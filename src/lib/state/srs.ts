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
import type { Card, Grade, SrsStatus, ReviewLogEntry } from './types';

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
  word_id: string;
  story_id: number;
  context_sentence_idx: number;
  now?: Date;
}): Card {
  const now = args.now ?? new Date();
  const empty = createEmptyCard(now);
  return {
    word_id: args.word_id,
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
  const item = recordLog[rating];
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
  /** Max NEW cards (status=new) introduced this session. Default 20. */
  maxNew?: number;
  /** Max REVIEW cards (status=young/mature/relearning/leech). Default 200. */
  maxReviews?: number;
  /**
   * Interleave ratio: roughly one new card every N review cards. Default 4.
   * Set to 0 to put all news at the end (Anki "after reviews").
   */
  newPerReview?: number;
  now?: Date;
}

/**
 * Build the review queue for a session.
 *
 * Sort:
 *   1. Learning + Relearning (short-term cards, intra-session priority).
 *      Sub-sort: oldest due first.
 *   2. Review cards (young/mature/leech). Sub-sort: most overdue first.
 *   3. New cards. Sub-sort: by word_id (stable).
 *
 * Then we apply caps and interleave "new" into the review stream.
 */
export function buildQueue(
  srs: Record<string, Card>,
  opts: QueueOptions = {},
): Card[] {
  const { maxNew = 20, maxReviews = 200, newPerReview = 4, now = new Date() } = opts;
  const t = now.getTime();

  const learning: Card[] = [];
  const reviews: Card[] = [];
  const news: Card[] = [];

  for (const card of Object.values(srs)) {
    if (!isDue(card, now)) continue;
    if (card.state === State.Learning || card.state === State.Relearning) {
      learning.push(card);
    } else if (card.state === State.Review) {
      reviews.push(card);
    } else {
      news.push(card);
    }
  }

  // Learning: oldest due first
  learning.sort((a, b) => new Date(a.due).getTime() - new Date(b.due).getTime());
  // Reviews: most overdue first (largest t-due)
  reviews.sort((a, b) => t - new Date(b.due).getTime() - (t - new Date(a.due).getTime()));
  // News: stable by word_id
  news.sort((a, b) => a.word_id.localeCompare(b.word_id));

  // Apply caps. Learning cards count against the review cap because they
  // are short-term cards that we MUST clear in this session — no point
  // exempting them and then never letting the user finish.
  const learningSlice = learning.slice(0, maxReviews);
  const cappedReviews = reviews.slice(0, Math.max(0, maxReviews - learningSlice.length));
  const cappedNews = news.slice(0, maxNew);

  // Interleave: learning at the very front (must clear short-term), then
  // weave news into the review stream at every Nth position.
  const woven: Card[] = [];
  let ni = 0;
  let ri = 0;
  while (ri < cappedReviews.length || ni < cappedNews.length) {
    // Place a new card every newPerReview reviews, or once reviews run out.
    if (
      ni < cappedNews.length &&
      newPerReview > 0 &&
      (ri === cappedReviews.length || (ri + ni) % (newPerReview + 1) === newPerReview)
    ) {
      woven.push(cappedNews[ni++]);
    } else if (ri < cappedReviews.length) {
      woven.push(cappedReviews[ri++]);
    } else {
      woven.push(cappedNews[ni++]);
    }
  }

  return [...learningSlice, ...woven];
}

/* ── Fuzz / jitter (intervals ≥ 1 day get ±5–10% noise) ────────── */

/**
 * Already applied internally by ts-fsrs (enable_fuzz: true). Re-exported
 * here for the read-view "new-card dribble" feature, which staggers
 * `due` times for newly-added cards by a small random delta.
 *
 * Returns a number of MILLISECONDS to add to `due`.
 */
export function dribbleOffset(index: number): number {
  // 0, 90s, 180s, ... up to ~5 minutes apart. Deterministic-ish so
  // batches of ten new cards from one story all have distinct due times
  // without falling outside the same review session.
  return Math.min(index, 30) * 90 * 1000;
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
