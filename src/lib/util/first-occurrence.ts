/**
 * Pure helpers for computing "is this token the FIRST occurrence of
 * its word_id in this scope?" — the data the read view feeds to
 * <Token isFirstInStory> to decide which tokens get the red
 * first-occurrence underline.
 *
 * Lives outside the Svelte components because (a) the same logic is
 * used by both `RubyHeader` (title scope) and `+page.svelte` (body
 * scope) and (b) it has had two regressions in one session — easier
 * to lock down with unit tests when it's a pure function.
 */
import type { Token } from '../data/types';

/**
 * Returns a map: token-array index → true iff this is the FIRST
 * occurrence of the token's `word_id` in the given token list.
 * Tokens with no word_id are mapped to `false`.
 */
export function firstOccurrenceInTokens(tokens: Token[] | undefined): Map<number, boolean> {
  const map = new Map<number, boolean>();
  if (!tokens) return map;
  const seen = new Set<string>();
  for (let i = 0; i < tokens.length; i += 1) {
    const wid = tokens[i].word_id;
    if (wid && !seen.has(wid)) {
      map.set(i, true);
      seen.add(wid);
    } else {
      map.set(i, false);
    }
  }
  return map;
}

/**
 * Returns a map: sentenceIdx → Set<tokenIdx>, where the inner set
 * contains the indices of tokens that are the FIRST occurrence of
 * their `word_id` across the entire ordered list of sentences.
 *
 * The title scope is intentionally separate: title and body each have
 * their own first-occurrence context. A word that appears in both
 * gets the underline in both. This was a deliberate product decision
 * after the body underline kept disappearing whenever a kanji title
 * happened to contain the same word.
 */
export function firstOccurrenceInSentences(
  sentences: { tokens: Token[] }[] | undefined,
): Map<number, Set<number>> {
  const map = new Map<number, Set<number>>();
  if (!sentences) return map;
  const seen = new Set<string>();
  for (let i = 0; i < sentences.length; i += 1) {
    const sentSet = new Set<number>();
    const sent = sentences[i];
    for (let ti = 0; ti < sent.tokens.length; ti += 1) {
      const tok = sent.tokens[ti];
      if (tok.word_id && !seen.has(tok.word_id)) {
        sentSet.add(ti);
        seen.add(tok.word_id);
      }
    }
    map.set(i, sentSet);
  }
  return map;
}
