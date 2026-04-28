/**
 * Pure filters for the "what has the learner actually seen" views.
 *
 * Both the vocab and grammar tabs default to showing only items the
 * learner has encountered (vocab → in srs; grammar → introduced in
 * some shipped story). The full catalogs are still available behind
 * a "Show all" toggle.
 *
 * Lives in util/ as pure functions so:
 *   1. The decision policy is testable without rendering Svelte.
 *   2. Future callers (e.g. an "Export my known words" button, a
 *      home-screen progress card) can reuse the same predicate.
 */
import type { Card } from '../state/types';
import type { GrammarPoint, VocabIndexRow } from '../data/types';

/**
 * A vocab row is "known" iff the learner has at least one SRS card
 * for it — i.e. has explicitly pressed "Save for review" on a story
 * containing that word. Status (new / learning / young / mature /
 * leech) is irrelevant: even a fresh "new" card means the learner
 * intends to learn it. Words the learner has seen on the page but
 * never saved are NOT known by this definition.
 */
export function isKnownWord(
  row: { id: string },
  srs: Record<string, Card> | undefined | null,
): boolean {
  if (!srs) return false;
  return !!srs[row.id];
}

export function filterKnownWords(
  rows: readonly VocabIndexRow[],
  srs: Record<string, Card> | undefined | null,
): VocabIndexRow[] {
  return rows.filter((r) => isKnownWord(r, srs));
}

/**
 * A grammar point is "seen" iff its intro_in_story field is a positive
 * integer — meaning the state-updater attributed it to some shipped
 * story. Null/undefined/0/negative all count as not-yet-seen.
 *
 * The check is on the GRAMMAR STATE, not on whether the learner has
 * actually opened that story; this matches the existing app-wide
 * convention that "seen" = "exists in the curriculum so far".
 */
export function isSeenGrammar(gp: Pick<GrammarPoint, 'intro_in_story'>): boolean {
  const n = gp.intro_in_story;
  return typeof n === 'number' && Number.isFinite(n) && n > 0;
}

export function filterSeenGrammar<T extends Pick<GrammarPoint, 'intro_in_story'>>(
  points: readonly T[],
): T[] {
  return points.filter(isSeenGrammar);
}
