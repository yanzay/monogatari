/**
 * Cross-cutting types for SRS, learner state, and the review log.
 *
 * Lives in its own file to avoid the circular dep between srs.ts and
 * learner.svelte.ts (both reference Card; learner imports srs for
 * helpers).
 */
import type { State } from 'ts-fsrs';

/* ── Grades (3-button: Again, Good, Easy) ─────────────────────── */

export type Grade = 0 | 1 | 2;

/* ── Status (UI label, derived from FSRS state + interval) ────── */

export type SrsStatus = 'new' | 'learning' | 'relearning' | 'young' | 'mature' | 'leech';

/* ── Card ─────────────────────────────────────────────────────── */

export interface Card {
  word_id: string;
  first_learned_story: number;
  context_story: number;
  context_sentence_idx: number;

  /** ISO timestamp of next due. */
  due: string;

  /** FSRS internals. */
  stability: number;
  difficulty: number;
  elapsed_days: number;
  scheduled_days: number;
  learning_steps: number;
  reps: number;
  lapses: number;
  /** FSRS state: 0=New, 1=Learning, 2=Review, 3=Relearning. */
  state: State;
  /** ISO timestamp of last review (undefined for never-reviewed). */
  last_review?: string;

  /** UI-derived label (cached). */
  status: SrsStatus;
}

/* ── Review log ───────────────────────────────────────────────── */

export interface ReviewLogEntry {
  word_id: string;
  grade: Grade;
  reviewed_at: string;
  /** Snapshot of the card BEFORE this review (used by Undo). */
  card_before: Card;
  /** Snapshot of the card AFTER this review (used by stats / debug). */
  card_after: Card;
}
