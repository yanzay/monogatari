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

/* ── Card kind (modality discriminator) ───────────────────────── */

/**
 * Distinguishes the two retention tracks the SRS now schedules:
 *
 *   - `'reading'` (default for legacy + word-keyed cards) — prompt is
 *     the highlighted word in its native sentence; user recalls
 *     reading + meaning. One card per minted word, keyed `<word_id>`.
 *
 *   - `'listening'` — prompt is the SENTENCE audio with no text; user
 *     recalls comprehension. One card per sentence of every read
 *     story, keyed `L:<story_id>:<sentence_idx>` so the SRS map can
 *     hold both modalities side-by-side without collision.
 *
 * Both kinds run through the same FSRS scheduler with independent
 * stability/difficulty — mixing modalities into one stability score
 * was the structural defect of the old "Listen first" toggle.
 *
 * Pre-2026-04-29 cards have no `kind` field; the sanitizer treats
 * absence as `'reading'` (the only kind that existed).
 */
export type CardKind = 'reading' | 'listening';

/* ── Card ─────────────────────────────────────────────────────── */

export interface Card {
  /**
   * Identifier for the SRS map key AND for the answer to display.
   *
   *   - reading cards: a word id like `W00042` — also indexes vocab.
   *   - listening cards: `L:<story_id>:<sentence_idx>` — encodes the
   *     sentence the audio comes from. The reviewer parses this back
   *     into (story, sentence) when loading the card.
   *
   * The field stays named `word_id` for backwards compat with existing
   * stored data, the review log, and helpers that key off it; treat it
   * as "card id" for listening cards. (Renaming would force a v3→v4
   * schema bump and drop every learner's progress, which is not worth
   * the cosmetic win.)
   */
  word_id: string;
  /**
   * Card kind / modality. Optional for migration: cards minted before
   * 2026-04-29 lack this field and are read as `'reading'`. The
   * sanitizer + helpers treat `undefined` as `'reading'`.
   */
  kind?: CardKind;
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

/** Build the SRS map key for a listening card. Pure helper so the
 *  format lives in exactly one place. */
export function listeningCardId(story_id: number, sentence_idx: number): string {
  return `L:${story_id}:${sentence_idx}`;
}

/** Inverse of listeningCardId. Returns null for ids that aren't
 *  listening cards (e.g. plain `W00042`). */
export function parseListeningCardId(
  id: string,
): { story_id: number; sentence_idx: number } | null {
  if (!id || !id.startsWith('L:')) return null;
  const parts = id.split(':');
  if (parts.length !== 3) return null;
  const sid = Number(parts[1]);
  const idx = Number(parts[2]);
  if (!Number.isInteger(sid) || !Number.isInteger(idx) || sid < 1 || idx < 0) return null;
  return { story_id: sid, sentence_idx: idx };
}

/** Card kind with safe default for legacy rows lacking the field. */
export function cardKind(card: Pick<Card, 'kind' | 'word_id'>): CardKind {
  if (card.kind === 'listening' || card.kind === 'reading') return card.kind;
  // Defensive fallback: a legacy card whose id starts with `L:` is a
  // listening card whose `kind` field was lost in transit. This can't
  // happen organically (no listening cards existed before this commit)
  // but it costs nothing to be correct.
  if (card.word_id?.startsWith('L:')) return 'listening';
  return 'reading';
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
