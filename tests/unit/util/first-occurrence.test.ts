/**
 * Regression tests for the first-occurrence helpers that drive the
 * red "new word" underline. Two bugs in two days here, both silent
 * (no error, just missing underline). Tests pin both:
 *
 *   1. (2026-04-28a) The body never got isFirstInStory=true because
 *      the read view didn't pass the prop at all.
 *   2. (2026-04-28b) The body STILL didn't get the underline for a
 *      word that also appeared in the title, because the body's
 *      seen-set was pre-loaded with title tokens AND the title's own
 *      seen-set was pre-loaded too — neither scope ever saw a
 *      "first" occurrence for kanji-titled words like 鍵 / The Key.
 *
 * Title scope and body scope are now intentionally independent.
 */
import { describe, it, expect } from 'vitest';
import {
  firstOccurrenceInTokens,
  firstOccurrenceInSentences,
} from '../../../src/lib/util/first-occurrence';
import type { Token } from '../../../src/lib/data/types';

const tok = (t: string, word_id?: string, role: Token['role'] = 'content'): Token => ({
  t,
  role,
  ...(word_id ? { word_id } : {}),
});

describe('firstOccurrenceInTokens', () => {
  it('returns an empty map for undefined input', () => {
    expect(firstOccurrenceInTokens(undefined).size).toBe(0);
  });

  it('returns an empty map for empty input', () => {
    expect(firstOccurrenceInTokens([]).size).toBe(0);
  });

  it('marks a single content token as first', () => {
    const m = firstOccurrenceInTokens([tok('鍵', 'W00001')]);
    expect(m.get(0)).toBe(true);
  });

  it('marks the FIRST occurrence true and repeats false', () => {
    // 「友達と友達」 — same word twice in the title.
    const m = firstOccurrenceInTokens([
      tok('友達', 'W00010'),
      tok('と', undefined, 'particle'),
      tok('友達', 'W00010'),
    ]);
    expect(m.get(0)).toBe(true);
    expect(m.get(1)).toBe(false);
    expect(m.get(2)).toBe(false);
  });

  it('returns false for tokens with no word_id (particles, punct)', () => {
    const m = firstOccurrenceInTokens([
      tok('猫', 'W00001'),
      tok('は', undefined, 'particle'),
      tok('。', undefined, 'punct'),
    ]);
    expect(m.get(0)).toBe(true);
    expect(m.get(1)).toBe(false);
    expect(m.get(2)).toBe(false);
  });

  it('handles two distinct words both as first', () => {
    const m = firstOccurrenceInTokens([
      tok('猫', 'W00001'),
      tok('と', undefined, 'particle'),
      tok('犬', 'W00002'),
    ]);
    expect(m.get(0)).toBe(true);
    expect(m.get(2)).toBe(true);
  });
});

describe('firstOccurrenceInSentences', () => {
  it('returns an empty map for undefined input', () => {
    expect(firstOccurrenceInSentences(undefined).size).toBe(0);
  });

  it('returns a map with one empty set per sentence when sentences are empty', () => {
    const m = firstOccurrenceInSentences([{ tokens: [] }, { tokens: [] }]);
    expect(m.size).toBe(2);
    expect(m.get(0)?.size).toBe(0);
    expect(m.get(1)?.size).toBe(0);
  });

  it('marks first occurrence in sentence 0', () => {
    const m = firstOccurrenceInSentences([
      { tokens: [tok('猫', 'W00001'), tok('は', undefined, 'particle')] },
    ]);
    expect(m.get(0)).toEqual(new Set([0]));
  });

  it('does NOT re-mark a word that already appeared in an earlier sentence', () => {
    const m = firstOccurrenceInSentences([
      { tokens: [tok('猫', 'W00001')] },
      { tokens: [tok('猫', 'W00001'), tok('犬', 'W00002')] },
    ]);
    expect(m.get(0)).toEqual(new Set([0]));
    // Sentence 1: 猫 already seen, 犬 is new.
    expect(m.get(1)).toEqual(new Set([1]));
  });

  describe('REGRESSION: title and body scopes are independent', () => {
    it('a word that appears in the title still gets first-occurrence in the body', () => {
      // This mirrors story 4 ("The Key", title=鍵, sentence 1 also uses 鍵).
      const titleTokens: Token[] = [tok('鍵', 'W00001')];
      const bodySentences = [
        {
          tokens: [
            tok('朝', 'W00002'),
            tok('、', undefined, 'punct'),
            tok('私', 'W00003'),
            tok('は', undefined, 'particle'),
            tok('鍵', 'W00001'),
            tok('を', undefined, 'particle'),
            tok('持ちます', 'W00009'),
            tok('。', undefined, 'punct'),
          ],
        },
      ];

      const titleMap = firstOccurrenceInTokens(titleTokens);
      const bodyMap = firstOccurrenceInSentences(bodySentences);

      // Title: 鍵 IS the first (and only) occurrence in title scope.
      expect(titleMap.get(0)).toBe(true);
      // Body: 鍵 (token index 4) IS the first occurrence in body scope.
      // Pre-fix this was false because the body seen-set was pre-loaded
      // with title tokens.
      expect(bodyMap.get(0)?.has(4)).toBe(true);
    });

    it('the body marks first occurrence even when EVERY new word also appears in the title', () => {
      // Pathological: title is the entire vocabulary inventory.
      const titleTokens: Token[] = [
        tok('猫', 'W001'),
        tok('と', undefined, 'particle'),
        tok('犬', 'W002'),
      ];
      const bodySentences = [
        { tokens: [tok('猫', 'W001'), tok('と', undefined, 'particle'), tok('犬', 'W002')] },
      ];
      const bodyMap = firstOccurrenceInSentences(bodySentences);
      // Both content tokens (0 and 2) should be first in body scope.
      expect(bodyMap.get(0)).toEqual(new Set([0, 2]));
    });
  });

  it('multi-sentence: word repeated across 3 sentences only marked first in sentence 0', () => {
    const m = firstOccurrenceInSentences([
      { tokens: [tok('鍵', 'W00001')] },
      { tokens: [tok('鍵', 'W00001')] },
      { tokens: [tok('鍵', 'W00001')] },
    ]);
    expect(m.get(0)?.has(0)).toBe(true);
    expect(m.get(1)?.size).toBe(0);
    expect(m.get(2)?.size).toBe(0);
  });
});
