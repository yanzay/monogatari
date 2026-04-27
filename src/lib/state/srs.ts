/**
 * Pure SRS scheduler. Internally uses MINUTES, not days, to avoid the
 * fractional-rounding bugs in the legacy implementation.
 *
 * Status ladder:
 *   new        → never reviewed
 *   learning   → interval < 1 day
 *   relearning → just lapsed (Again grade)
 *   young      → 1 day ≤ interval < 21 days
 *   mature     → interval ≥ 21 days
 *   leech      → lapses ≥ 6 (sticky)
 */

export type Grade = 0 | 1 | 2 | 3;

export const GRADES = {
  AGAIN: 0 as Grade,
  HARD: 1 as Grade,
  GOOD: 2 as Grade,
  EASY: 3 as Grade,
};

export type SrsStatus = 'new' | 'learning' | 'relearning' | 'young' | 'mature' | 'leech';

export interface Card {
  word_id: string;
  first_learned_story: number;
  context_story: number;
  context_sentence_idx: number;
  /** Interval in MINUTES until next review. */
  interval_min: number;
  ease: number;
  reps: number;
  lapses: number;
  status: SrsStatus;
  /** ISO timestamp of next due. */
  due: string;
}

const MIN_PER_DAY = 24 * 60;
const EASE_FLOOR = 1.3;
const EASE_CEIL = 4.0;
const LEECH_THRESHOLD = 6;
/** Hard ceiling on interval to prevent Date overflow on long EASY chains. */
const MAX_INTERVAL_MIN = 100 * 365 * MIN_PER_DAY; // 100 years

export function newCard(args: {
  word_id: string;
  story_id: number;
  context_sentence_idx: number;
  now?: Date;
}): Card {
  const now = args.now ?? new Date();
  return {
    word_id: args.word_id,
    first_learned_story: args.story_id,
    context_story: args.story_id,
    context_sentence_idx: args.context_sentence_idx,
    interval_min: 0,
    ease: 2.5,
    reps: 0,
    lapses: 0,
    status: 'new',
    due: now.toISOString(),
  };
}

export function applyGrade(card: Card, grade: Grade, now: Date = new Date()): Card {
  let { interval_min, ease, reps, lapses } = card;

  switch (grade) {
    case GRADES.AGAIN:
      reps = 0;
      interval_min = 10;
      ease = Math.max(EASE_FLOOR, ease - 0.2);
      lapses += 1;
      break;
    case GRADES.HARD:
      // Hard: scale current interval by 1.2, but enforce a floor of 10 min
      // for cards that haven't graduated yet (interval_min < 1 day).
      interval_min =
        interval_min < MIN_PER_DAY
          ? Math.max(10, Math.round(interval_min * 1.2))
          : Math.round(interval_min * 1.2);
      ease = Math.max(EASE_FLOOR, ease - 0.15);
      break;
    case GRADES.GOOD:
      if (reps === 0) interval_min = 1 * MIN_PER_DAY;
      else if (reps === 1) interval_min = 3 * MIN_PER_DAY;
      else interval_min = Math.round(interval_min * ease);
      reps += 1;
      break;
    case GRADES.EASY:
      if (reps === 0) interval_min = 1 * MIN_PER_DAY;
      else if (reps === 1) interval_min = 3 * MIN_PER_DAY;
      else interval_min = Math.round(interval_min * ease);
      reps += 1;
      interval_min = Math.round(interval_min * 1.3);
      ease = Math.min(EASE_CEIL, ease + 0.1);
      break;
  }

  if (interval_min > MAX_INTERVAL_MIN) interval_min = MAX_INTERVAL_MIN;

  // Status: leech wins; otherwise relearning > learning > young > mature.
  let status: SrsStatus;
  if (lapses >= LEECH_THRESHOLD) status = 'leech';
  else if (grade === GRADES.AGAIN) status = 'relearning';
  else if (interval_min < MIN_PER_DAY) status = 'learning';
  else if (interval_min < 21 * MIN_PER_DAY) status = 'young';
  else status = 'mature';

  const due = new Date(now.getTime() + interval_min * 60 * 1000).toISOString();

  return { ...card, interval_min, ease, reps, lapses, status, due };
}

/** True when a card is due for review at `now`. Defends against Invalid Date. */
export function isDue(card: Pick<Card, 'due'>, now: Date = new Date()): boolean {
  if (!card.due) return true;
  const t = new Date(card.due).getTime();
  if (!Number.isFinite(t)) return true;
  return t <= now.getTime();
}

/**
 * Migrate a legacy card that stored `interval_days`. Idempotent: if the
 * card already has `interval_min`, returns it unchanged.
 */
export function migrateCard(raw: any): Card {
  if (!raw || typeof raw !== 'object') {
    throw new Error('migrateCard: not an object');
  }
  if (typeof raw.interval_min === 'number') {
    return raw as Card;
  }
  const days = typeof raw.interval_days === 'number' ? raw.interval_days : 0;
  return {
    word_id: String(raw.word_id ?? ''),
    first_learned_story: Number(raw.first_learned_story ?? 0),
    context_story: Number(raw.context_story ?? raw.first_learned_story ?? 0),
    context_sentence_idx: Number(raw.context_sentence_idx ?? 0),
    interval_min: Math.round(days * MIN_PER_DAY),
    ease: typeof raw.ease === 'number' ? raw.ease : 2.5,
    reps: typeof raw.reps === 'number' ? raw.reps : 0,
    lapses: typeof raw.lapses === 'number' ? raw.lapses : 0,
    status: ((): SrsStatus => {
      const s = raw.status;
      const valid: SrsStatus[] = ['new', 'learning', 'relearning', 'young', 'mature', 'leech'];
      return valid.includes(s) ? s : 'new';
    })(),
    due: typeof raw.due === 'string' ? raw.due : new Date().toISOString(),
  };
}
