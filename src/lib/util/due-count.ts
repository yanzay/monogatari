/**
 * Pure helper: count how many SRS cards are due at a given moment.
 *
 * Lives outside +layout.svelte for two reasons:
 *   1. The badge had a real bug (2026-04-29) where it only updated on
 *      full page reload because the inline derivation called
 *      Date.now() directly — Date.now() isn't a reactive dependency,
 *      so the count went stale as time passed even though the SRS
 *      map was reactive. Centralizing the "now" parameter forces
 *      callers to think about clock-tick reactivity explicitly.
 *   2. The same predicate runs in three places: the layout's review-
 *      tab badge, the read view's "N due word here" CTA, and the
 *      review queue builder. Pinning it once means a future tweak
 *      (e.g. "include cards becoming due in the next 60s") only
 *      changes one file.
 *
 * A card is due when its `due` timestamp is unset, malformed, or
 * <= now. The `unset` clause matches FSRS's "fresh card" shape
 * before any review has happened.
 */
import type { Card } from '../state/types';
import { cardKind } from '../state/types';
import type { CardKind } from '../state/types';

export function isCardDue(card: Card | null | undefined, now: Date | number): boolean {
  if (!card) return false;
  if (!card.due) return true;
  const t = new Date(card.due).getTime();
  if (!Number.isFinite(t)) return true;
  const cmp = typeof now === 'number' ? now : now.getTime();
  return t <= cmp;
}

export function countDueCards(
  srs: Record<string, Card> | undefined | null,
  now: Date | number,
): number {
  if (!srs) return 0;
  let n = 0;
  for (const card of Object.values(srs)) {
    if (isCardDue(card, now)) n += 1;
  }
  return n;
}

/**
 * Count due cards of a specific kind (modality).
 *
 * Used by the nav badges to show separate reading and listening
 * due-counts, so "Review 5" and "Listen 3" are independently
 * meaningful rather than summed into a single confusing number.
 */
export function countDueByKind(
  srs: Record<string, Card> | undefined | null,
  now: Date | number,
  kind: CardKind,
): number {
  if (!srs) return 0;
  let n = 0;
  for (const card of Object.values(srs)) {
    if (cardKind(card) === kind && isCardDue(card, now)) n += 1;
  }
  return n;
}

/**
 * Returns the epoch-ms timestamp of the next moment when the
 * due-count would change — i.e. the earliest `card.due` strictly
 * greater than `now`. Callers use this to schedule a single, precise
 * setTimeout instead of polling on a fixed cadence.
 *
 * Returns null when no card is pending in the future (every card is
 * already due, or the srs map is empty/null). The caller should NOT
 * schedule any timer in that case — there's nothing to wait for.
 *
 * Cards with no `due`, malformed `due`, or `due <= now` are treated
 * as already-due (consistent with isCardDue) and do NOT contribute.
 */
export function nextDueChangeTimestamp(
  srs: Record<string, Card> | undefined | null,
  now: Date | number,
): number | null {
  if (!srs) return null;
  const cmp = typeof now === 'number' ? now : now.getTime();
  let earliest = Infinity;
  for (const card of Object.values(srs)) {
    if (!card?.due) continue;
    const t = new Date(card.due).getTime();
    if (!Number.isFinite(t)) continue;
    if (t > cmp && t < earliest) earliest = t;
  }
  return Number.isFinite(earliest) ? earliest : null;
}
