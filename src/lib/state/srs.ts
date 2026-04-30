/**
 * Monogatari SRS — FSRS-5 wrapper.
 *
 * Why FSRS: SM-2 (the previous scheduler) is the 1987 algorithm Anki
 * used to ship by default. FSRS is the modern data-driven successor
 * (Anki adopted it as default in 23.10) and reduces review burden by
 * ~25-35% at the same retention target. The reference TypeScript
 * implementation `ts-fsrs` is MIT licensed and ~10 KB minified.
 *
 * Public API (intentionally narrow):
 *   newCard(args)         — create a fresh New card, due immediately
 *   applyGrade(card, g)   — apply user rating, return next-state card
 *   isDue(card, now?)     — predicate
 *   buildQueue(srs, opts) — sort + cap + interleave for the review view
 *   fuzzInterval(min)     — small ±jitter so cards don't bunch up
 *
 * Card shape lives in src/lib/state/types.ts. It is a superset of the
 * FSRS card with our own `word_id` and context pointers attached.
 *
 * Migration: NONE. Per product call, existing learner state from the
 * SM-2 era is dropped on version bump (learner.state.version 2→3).
 * See learner.svelte.ts for the gating.
 */
import {
  fsrs as makeFsrs,
  generatorParameters,
  createEmptyCard,
  Rating,
  State,
  type FSRS,
  type Card as FsrsCard,
} from 'ts-fsrs';
import type { Card, CardKind, Grade, SrsStatus, ReviewLogEntry } from './types';
import { cardKind, listeningCardId } from './types';
import type { Story } from '../data/types';

/* ── Configuration ───────────────────────────────────────────────── */

/** Default desired retention (FSRS calls this `request_retention`). */
export const DEFAULT_TARGET_RETENTION = 0.9;

/** Hard ceiling on interval (in DAYS) to prevent Date overflow. */
const MAX_INTERVAL_DAYS = 36500; // 100 years

/** Cards become "mature" at >= this many days of interval. */
const MATURE_THRESHOLD_DAYS = 21;

/** Lapse count at which a card is flagged "leech". Sticky: never clears. */
const LEECH_THRESHOLD = 6;

/* ── Grade enum (3-button: Again / Good / Easy — Hard dropped) ──── */

export const GRADES = {
  AGAIN: 0 as Grade,
  GOOD: 1 as Grade,
  EASY: 2 as Grade,
} as const;

const GRADE_TO_FSRS_RATING: Record<Grade, Rating> = {
  0: Rating.Again,
  1: Rating.Good,
  2: Rating.Easy,
};

/* ── Singleton scheduler (stateless; reuse-safe) ────────────────── */

let _fsrs: FSRS | null = null;
let _fsrsRetention = DEFAULT_TARGET_RETENTION;
function fsrsFor(retention: number): FSRS {
  if (_fsrs && _fsrsRetention === retention) return _fsrs;
  _fsrs = makeFsrs(
    generatorParameters({
      request_retention: retention,
      enable_fuzz: true,
      enable_short_term: true,
      maximum_interval: MAX_INTERVAL_DAYS,
    }),
  );
  _fsrsRetention = retention;
  return _fsrs;
}

/* ── Card factories ─────────────────────────────────────────────── */

/** Map FSRS state → our SrsStatus, layered on top with mature/leech. */
function statusFor(card: { state: State; lapses: number; scheduled_days: number }): SrsStatus {
  if (card.lapses >= LEECH_THRESHOLD) return 'leech';
  switch (card.state) {
    case State.New:
      return 'new';
    case State.Learning:
      return 'learning';
    case State.Relearning:
      return 'relearning';
    case State.Review:
      return card.scheduled_days >= MATURE_THRESHOLD_DAYS ? 'mature' : 'young';
    default:
      return 'new';
  }
}

export function newCard(args: {
  /** SRS map key. For reading cards this is the word_id; for listening
   *  cards it's `listeningCardId(story_id, sentence_idx)`. */
  word_id: string;
  story_id: number;
  context_sentence_idx: number;
  /** Defaults to `'reading'` for backwards compat with the only
   *  pre-2026-04-29 caller. */
  kind?: CardKind;
  now?: Date;
}): Card {
  const now = args.now ?? new Date();
  const empty = createEmptyCard(now);
  return {
    word_id: args.word_id,
    kind: args.kind ?? 'reading',
    first_learned_story: args.story_id,
    context_story: args.story_id,
    context_sentence_idx: args.context_sentence_idx,
    due: empty.due.toISOString(),
    stability: empty.stability,
    difficulty: empty.difficulty,
    elapsed_days: empty.elapsed_days,
    scheduled_days: empty.scheduled_days,
    learning_steps: (empty as any).learning_steps ?? 0,
    reps: empty.reps,
    lapses: empty.lapses,
    state: empty.state,
    last_review: undefined,
    status: 'new',
  };
}

/* ── Apply grade ─────────────────────────────────────────────────── */

function toFsrsCard(card: Card): FsrsCard {
  return {
    due: new Date(card.due),
    stability: card.stability,
    difficulty: card.difficulty,
    elapsed_days: card.elapsed_days,
    scheduled_days: card.scheduled_days,
    learning_steps: card.learning_steps ?? 0,
    reps: card.reps,
    lapses: card.lapses,
    state: card.state,
    last_review: card.last_review ? new Date(card.last_review) : undefined,
  };
}

function fromFsrsCard(base: Card, next: FsrsCard, now: Date): Card {
  const status = statusFor({
    state: next.state,
    lapses: next.lapses,
    scheduled_days: next.scheduled_days,
  });
  return {
    ...base,
    due: next.due.toISOString(),
    stability: next.stability,
    difficulty: next.difficulty,
    elapsed_days: next.elapsed_days,
    scheduled_days: next.scheduled_days,
    learning_steps: (next as any).learning_steps ?? 0,
    reps: next.reps,
    lapses: next.lapses,
    state: next.state,
    last_review: now.toISOString(),
    status,
  };
}

/**
 * Apply a grade to a card. Returns BOTH the next card AND a review-log
 * entry the caller is expected to persist (used for Undo and for
 * statistics / future per-user FSRS optimization).
 */
export function applyGrade(
  card: Card,
  grade: Grade,
  now: Date = new Date(),
  retention: number = DEFAULT_TARGET_RETENTION,
): { card: Card; log: ReviewLogEntry } {
  const fsrs = fsrsFor(retention);
  const fsrsCard = toFsrsCard(card);
  const recordLog = fsrs.repeat(fsrsCard, now);
  const rating = GRADE_TO_FSRS_RATING[grade];
  // ts-fsrs's IPreview is keyed by their internal Grade enum (Again|Hard|
  // Good|Easy = 1..4), narrower than Rating (which also has Manual=0).
  // GRADE_TO_FSRS_RATING never produces Manual so the index is safe at
  // runtime; we go through `unknown` to suppress the strict overlap
  // check (TypeScript can't see that we never pass Manual through).
  const item = (recordLog as unknown as Partial<Record<Rating, { card: FsrsCard }>>)[rating];
  if (!item) {
    throw new Error(`FSRS returned no item for grade ${grade}`);
  }
  const nextCard = fromFsrsCard(card, item.card, now);

  const log: ReviewLogEntry = {
    word_id: card.word_id,
    grade,
    reviewed_at: now.toISOString(),
    card_before: card,
    card_after: nextCard,
  };
  return { card: nextCard, log };
}

/* ── Queue building ─────────────────────────────────────────────── */

/** True when a card is due for review at `now`. Defends against Invalid Date. */
export function isDue(card: Pick<Card, 'due'>, now: Date = new Date()): boolean {
  if (!card.due) return true;
  const t = new Date(card.due).getTime();
  if (!Number.isFinite(t)) return true;
  return t <= now.getTime();
}

export interface QueueOptions {
  /**
   * Max REVIEW cards (status=young/mature/relearning/leech) per session.
   * Default Infinity (no cap). The previous default (200, Anki-inherited)
   * was clipping due cards out of sessions when the user had a long
   * backlog; the user almost always wants to see every due card. Pass
   * a positive integer to opt into a session cap.
   *
   * The previous `maxNew` cap was removed for the same reason — see
   * Prefs.daily_max_reviews docstring for the full rationale. New cards
   * in this app are cards the user just deliberately read; throttling
   * their introduction is the app overruling its own user.
   *
   * The cap counts BOTH reading and listening review cards together —
   * both modalities cost the user the same per-card effort and a single
   * cap matches the intuitive "I want at most N cards in a session".
   */
  maxReviews?: number;
  /**
   * Interleave ratio: roughly one new card every N review cards. Default 4.
   * Set to 0 to put all news at the end (Anki "after reviews").
   */
  newPerReview?: number;
  /**
   * Listening-card interleave: one listening card every N reading cards.
   * Default 6 (so a typical session of ~12-18 reading cards picks up
   * 2-3 listening prompts). Set to 0 to drop all listening cards from
   * the queue — the user opted out at the prefs level.
   *
   * Listening cards live on the same FSRS scheduler but a separate
   * deck. They never replace a reading card; they're woven IN. A
   * session that's 0% listening (because none are due, or the pref is
   * 0) is identical to the pre-2026-04-29 reading-only queue.
   */
  listeningPerReview?: number;
  now?: Date;
}

/**
 * Build the review queue for a session.
 *
 * Sort:
 *   1. Learning + Relearning READING cards (short-term, intra-session
 *      priority). Sub-sort: oldest due first.
 *   2. Review READING cards (young/mature/leech). Sub-sort: most
 *      overdue first.
 *   3. New READING cards. Sub-sort: by word_id (stable).
 *   4. Listening cards (any status). Sub-sort: most overdue first,
 *      then by id for stable ordering.
 *
 * Reading cards are then capped + interleaved as before. Listening
 * cards are woven into the resulting reading stream at the
 * `listeningPerReview` rate so they never replace reading cards —
 * they're additive, matching the product call that listening should
 * be addition not choice.
 *
 * Listening learning/relearning cards (i.e. you got an Again on a
 * listening prompt) get the same intra-session priority as reading
 * learning cards: they're hoisted to the front so the user can clear
 * the short-term debt before fresh material.
 */
export function buildQueue(
  srs: Record<string, Card>,
  opts: QueueOptions = {},
): Card[] {
  const {
    maxReviews = Infinity,
    newPerReview = 4,
    listeningPerReview = 6,
    now = new Date(),
  } = opts;
  const t = now.getTime();

  // Reading buckets.
  const learning: Card[] = [];
  const reviews: Card[] = [];
  const news: Card[] = [];
  // Listening buckets (separate so the rate-based interleave is clean).
  const listenLearning: Card[] = [];
  const listenReviews: Card[] = [];
  const listenNews: Card[] = [];

  for (const card of Object.values(srs)) {
    if (!isDue(card, now)) continue;
    const isListen = cardKind(card) === 'listening';
    if (card.state === State.Learning || card.state === State.Relearning) {
      (isListen ? listenLearning : learning).push(card);
    } else if (card.state === State.Review) {
      (isListen ? listenReviews : reviews).push(card);
    } else {
      (isListen ? listenNews : news).push(card);
    }
  }

  // Reading sub-sorts (unchanged).
  learning.sort((a, b) => new Date(a.due).getTime() - new Date(b.due).getTime());
  reviews.sort((a, b) => t - new Date(b.due).getTime() - (t - new Date(a.due).getTime()));
  news.sort((a, b) => a.word_id.localeCompare(b.word_id));
  // Listening sub-sorts: same predicates.
  listenLearning.sort((a, b) => new Date(a.due).getTime() - new Date(b.due).getTime());
  listenReviews.sort((a, b) => t - new Date(b.due).getTime() - (t - new Date(a.due).getTime()));
  listenNews.sort((a, b) => a.word_id.localeCompare(b.word_id));

  // Apply caps. Both reading and listening review cards count against
  // the same cap so the user's "I want N cards per session" request is
  // honored as a TOTAL, not a per-modality multiplier.
  // Learning cards (both kinds) count against the cap because they're
  // short-term and we MUST clear them — see original rationale above.
  // Reading learning fills first (matches the legacy ordering pinned
  // by buildQueue's "learning + relearning come first" test), then
  // listening learning, then reviews fill the remainder.
  const learnSliceR = learning.slice(0, maxReviews);
  const learnSliceL = listenLearning.slice(
    0,
    Math.max(0, maxReviews - learnSliceR.length),
  );
  const learnTotal = learnSliceR.length + learnSliceL.length;
  const reviewBudget = Math.max(0, maxReviews - learnTotal);
  // Split the review budget. Fill reading reviews first up to its
  // share, then top off with listening reviews. This matches the
  // user-facing principle that reading is the primary skill and
  // listening rides along.
  const cappedReviews = reviews.slice(0, reviewBudget);
  const cappedListenReviews = listenReviews.slice(
    0,
    Math.max(0, reviewBudget - cappedReviews.length),
  );
  // News are uncapped (both kinds) — the user just opted into them.
  const cappedNews = news;
  const cappedListenNews = listenNews;

  // First weave: reading cards into a single ordered stream (existing
  // behavior — interleave new among reviews at newPerReview cadence).
  const reading: Card[] = [];
  {
    let ni = 0;
    let ri = 0;
    while (ri < cappedReviews.length || ni < cappedNews.length) {
      if (
        ni < cappedNews.length &&
        newPerReview > 0 &&
        (ri === cappedReviews.length || (ri + ni) % (newPerReview + 1) === newPerReview)
      ) {
        reading.push(cappedNews[ni++]);
      } else if (ri < cappedReviews.length) {
        reading.push(cappedReviews[ri++]);
      } else {
        reading.push(cappedNews[ni++]);
      }
    }
  }

  // Second weave: listening reviews + new into the reading stream at
  // the listeningPerReview cadence. listening news interleave at the
  // SAME cadence — there are far fewer of them than reading news so
  // a single shared rate keeps the math (and the user mental model)
  // simple.
  const listenStream: Card[] = [...cappedListenReviews, ...cappedListenNews];
  const woven: Card[] = [];
  if (listeningPerReview <= 0 || listenStream.length === 0) {
    woven.push(...reading, ...listenStream); // listening always at end if any leak in
    if (listeningPerReview <= 0) woven.length = reading.length; // hard drop when pref=0
  } else {
    let li = 0;
    let ri = 0;
    while (ri < reading.length || li < listenStream.length) {
      if (
        li < listenStream.length &&
        (ri === reading.length || (ri + li) % (listeningPerReview + 1) === listeningPerReview)
      ) {
        woven.push(listenStream[li++]);
      } else if (ri < reading.length) {
        woven.push(reading[ri++]);
      } else {
        woven.push(listenStream[li++]);
      }
    }
  }

  // Both flavors of learning (reading + listening) hoist to the very
  // front. Reading learning first because the existing test pins that
  // ordering, then listening learning behind it.
  return [...learnSliceR, ...learnSliceL, ...woven];
}

/* ── Fuzz / jitter (intervals ≥ 1 day get ±5–10% noise) ────────── */

/**
 * Returns a number of MILLISECONDS to add to a new card's `due` time
 * to spread a batch of fresh cards across the start of the next review
 * session. Currently RETAINED for backwards compatibility with stored
 * data and any external callers, but `mintCardsForStory` no longer
 * applies it (see that function's note).
 */
export function dribbleOffset(index: number): number {
  // 0, 90s, 180s, ... up to ~5 minutes apart.
  return Math.min(index, 30) * 90 * 1000;
}

/**
 * Mint fresh SRS cards for every word in `story.new_words` that does
 * not already have an entry in `srs`. Pure: returns a new srs map,
 * does not mutate the input.
 *
 * Each minted card's `due` is `now` — the cards are immediately
 * available for review. (Earlier versions added `dribbleOffset(i)` to
 * push later cards minutes into the future, but that meant pressing
 * "Save for review" on a 10-word story made the read-view's
 * "N due word here" CTA and the menu's review badge both read "1"
 * for the next ~15 minutes — actively misleading the learner about
 * what's available. Card ordering across the resulting review session
 * is `buildQueue`'s job; it sorts new cards stably by word_id.)
 *
 * The card's `context_sentence_idx` points at the FIRST sentence in
 * the story that contains the word — the read-back UI uses this to
 * jump to the source sentence on review.
 *
 * Also mints LISTENING cards — one per sentence in the story that has
 * audio. Listening cards live in the same map keyed
 * `L:<story_id>:<sentence_idx>` and are scheduled by the same FSRS
 * config but on independent stability/difficulty curves so the two
 * modalities don't contaminate each other's retention model.
 *
 * If `mintListening` is false, only reading cards are minted (kept as
 * an escape hatch for callers who want the legacy behavior — e.g. a
 * future "reading-only mode" preference). Default true.
 *
 * Skipping rules for listening cards:
 *   - already in `srs` (duplicate mint is a no-op, same as reading).
 *   - sentence has no `audio` field (no source material to prompt
 *     with). The decorateWithAudioPaths corpus helper synthesizes
 *     audio paths for every sentence when missing, so in practice
 *     this only skips when the corpus loader hasn't decorated yet.
 */
export function mintCardsForStory(
  story: Story,
  srs: Record<string, Card>,
  now: Date = new Date(),
): Record<string, Card> {
  // Only reading cards are minted at "Save for review" time. Listening
  // cards are deferred until every word in the sentence is mature —
  // prompting a learner to comprehend a sentence they just looked up
  // is a cold-listening test, not comprehension review. The deferred
  // mint is handled by tickListeningMinting(), which is called after
  // every grade in the review page and on boot.
  const next = { ...srs };
  for (const wid of story.new_words) {
    if (next[wid]) continue;
    const sentIdx = story.sentences.findIndex((s) =>
      s.tokens.some((t) => t.word_id === wid),
    );
    next[wid] = newCard({
      word_id: wid,
      story_id: story.story_id,
      context_sentence_idx: sentIdx,
      kind: 'reading',
      now,
    });
  }
  return next;
}

/**
 * The maturity gate for listening-card minting.
 *
 * A sentence is ready for a listening card when EVERY content word
 * in it is `mature` on the reading deck — meaning FSRS has scheduled
 * it out ≥ MATURE_THRESHOLD_DAYS days, i.e. the learner has truly
 * internalized each word's reading→meaning association and is ready
 * to encounter the sentence purely by ear.
 *
 * Words with no SRS row (unknown to the reading deck entirely) block
 * the sentence — this catches words that appear in a story the user
 * hasn't saved for review yet, preventing listening cards from being
 * minted for sentences that haven't been studied at all.
 *
 * @param sentence The sentence to check (from Story.sentences).
 * @param srs      The learner's SRS map.
 * @returns true when every content word is mature; false otherwise.
 */
export function sentenceListeningReady(
  sentence: { tokens: Array<{ word_id?: string }> },
  srs: Record<string, Card>,
): boolean {
  const wordIds = sentence.tokens
    .map((t) => t.word_id)
    .filter((id): id is string => !!id);
  if (wordIds.length === 0) return false; // No content words at all (punctuation-only) — skip.
  for (const wid of wordIds) {
    const card = srs[wid];
    if (!card) return false; // Word not yet in the reading deck → block.
    if (card.status !== 'mature') return false;
  }
  return true;
}

/**
 * Check whether any listening cards are now eligible to be minted
 * for the given story (i.e. every word in their sentence is mature
 * on the reading deck) and mint them if so.
 *
 * This is the deferred-mint path: called after every grade in the
 * review page and once on boot, so listening cards dribble in
 * naturally as the learner's reading mastery grows, rather than all
 * at once when a story is first saved.
 *
 * Pure: returns a new SRS map. No-op (returns the same reference)
 * when nothing new would be minted — callers can use reference
 * equality to avoid spurious saves.
 *
 * @param story The story whose sentences to check.
 * @param srs   The current SRS map.
 * @param now   Clock reference (default: new Date()).
 * @returns A new SRS map (or the same reference if nothing changed).
 */
export function tickListeningMinting(
  story: Story,
  srs: Record<string, Card>,
  now: Date = new Date(),
): Record<string, Card> {
  let next = srs;
  for (let i = 0; i < story.sentences.length; i++) {
    const sent = story.sentences[i];
    // Skip sentences without audio (no source material).
    if (!sent.audio) continue;
    const id = listeningCardId(story.story_id, i);
    // Already minted — skip (idempotent).
    if (next[id]) continue;
    // Gate: every content word must be mature.
    if (!sentenceListeningReady(sent, srs)) continue;
    // First mint — lazily copy on write so the no-op path costs nothing.
    if (next === srs) next = { ...srs };
    next[id] = newCard({
      word_id: id,
      story_id: story.story_id,
      context_sentence_idx: i,
      kind: 'listening',
      now,
    });
  }
  return next;
}

/* ── Stats helpers ──────────────────────────────────────────────── */

/** True retention over the last `windowDays` days, computed from the
 *  review log. A "successful" review is any grade > 0 (anything not Again). */
export function trueRetention(
  log: ReviewLogEntry[],
  windowDays = 30,
  now: Date = new Date(),
): { reviewed: number; remembered: number; rate: number } {
  const cutoff = now.getTime() - windowDays * 86400 * 1000;
  // Only count cards that had been seen at least once before — we exclude
  // first-ever sightings (which always "succeed" or "fail" regardless of
  // memory), matching Anki's "true retention" definition.
  let reviewed = 0;
  let remembered = 0;
  for (const r of log) {
    const t = new Date(r.reviewed_at).getTime();
    if (!Number.isFinite(t) || t < cutoff) continue;
    if (r.card_before.reps === 0) continue; // first-ever sighting
    reviewed += 1;
    if (r.grade > 0) remembered += 1;
  }
  return { reviewed, remembered, rate: reviewed === 0 ? 0 : remembered / reviewed };
}

/** Cards due each day for the next N days (forecast bar chart). */
export function dueForecast(
  srs: Record<string, Card>,
  days = 14,
  now: Date = new Date(),
): { day: string; count: number }[] {
  const buckets = Array.from({ length: days }, (_, i) => {
    const d = new Date(now);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + i);
    return { day: d.toISOString().slice(0, 10), count: 0, _ms: d.getTime() };
  });
  const cutoff = buckets[buckets.length - 1]._ms + 86400 * 1000;
  for (const card of Object.values(srs)) {
    const t = new Date(card.due).getTime();
    if (!Number.isFinite(t) || t >= cutoff) continue;
    if (t < buckets[0]._ms) {
      buckets[0].count += 1; // overdue → today
    } else {
      const idx = Math.floor((t - buckets[0]._ms) / (86400 * 1000));
      buckets[idx].count += 1;
    }
  }
  return buckets.map(({ day, count }) => ({ day, count }));
}

/** Aggregate counts by status for the stats view. */
export function statusCounts(srs: Record<string, Card>): Record<SrsStatus, number> {
  const counts: Record<SrsStatus, number> = {
    new: 0,
    learning: 0,
    relearning: 0,
    young: 0,
    mature: 0,
    leech: 0,
  };
  for (const c of Object.values(srs)) counts[c.status] = (counts[c.status] ?? 0) + 1;
  return counts;
}
