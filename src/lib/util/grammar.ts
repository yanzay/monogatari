import type { GrammarPoint } from '$lib/data/types';

const PLACEHOLDER_SHORTS = new Set([
  '(added by state updater — fill in description)',
  '(added by state updater)',
  'TODO',
  '',
]);

export function isGrammarEntryIncomplete(gp: GrammarPoint | undefined | null): boolean {
  if (!gp) return true;
  if (gp._needs_review) return true;
  if (!gp.title || gp.title.trim() === gp.id) return true;
  if (!gp.short || PLACEHOLDER_SHORTS.has(gp.short.trim())) return true;
  if (!gp.long || !gp.long.trim()) return true;
  return false;
}
