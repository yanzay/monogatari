/**
 * Regression tests for the word-audio path helper.
 *
 * BUG (2026-04-29 part 1): the WordPopup's "▶ play word" button never
 * appeared because the +layout.svelte invocation passed `story={null}`
 * and the popup derived audioSrc from `story?.word_audio?.[id]`. Empty.
 *
 * REFACTOR (2026-04-29 part 2): word audio was decoupled from any
 * story. Files now live in a flat `audio/words/<id>.mp3` directory
 * regardless of which story introduced the word. This avoids:
 *   - tying audio path to first_story (which can change after a
 *     corpus rewrite),
 *   - making audio undiscoverable from non-read screens (vocab list,
 *     library, review queue),
 *   - duplicate audio when the same word is referenced from multiple
 *     stories.
 *
 * The helper is deliberately tiny — id in, path out — and these tests
 * pin the contract.
 */
import { describe, it, expect } from 'vitest';
import { wordAudioPath } from '../../../src/lib/util/word-audio';

describe('wordAudioPath', () => {
  describe('null-safety', () => {
    it('returns null for null', () => {
      expect(wordAudioPath(null)).toBeNull();
    });

    it('returns null for undefined', () => {
      expect(wordAudioPath(undefined)).toBeNull();
    });

    it('returns null when id is missing', () => {
      expect(wordAudioPath({})).toBeNull();
    });

    it('returns null when id is an empty string', () => {
      expect(wordAudioPath({ id: '' })).toBeNull();
    });

    it('returns null when id is whitespace-only', () => {
      expect(wordAudioPath({ id: '   ' })).toBeNull();
    });

    it('returns null when id is the wrong type', () => {
      expect(wordAudioPath({ id: 42 as unknown as string })).toBeNull();
      expect(wordAudioPath({ id: null as unknown as string })).toBeNull();
    });
  });

  describe('flat per-word directory', () => {
    it('builds the canonical path for a 5-digit word id', () => {
      expect(wordAudioPath({ id: 'W00001' })).toBe('audio/words/W00001.mp3');
    });

    it('does NOT depend on first_story (decoupled by design)', () => {
      // Same id should always map to the same path regardless of any
      // metadata about which story introduced the word. This was the
      // whole point of the 2026-04-29 refactor.
      expect(wordAudioPath({ id: 'W00021', first_story: 4 } as { id: string })).toBe(
        'audio/words/W00021.mp3',
      );
      expect(
        wordAudioPath({ id: 'W00021', first_story: 'story_4' } as { id: string }),
      ).toBe('audio/words/W00021.mp3');
      // Even when first_story is missing entirely, the path resolves.
      expect(wordAudioPath({ id: 'W00021' })).toBe('audio/words/W00021.mp3');
    });

    it('handles an arbitrary string id (not just W#####)', () => {
      // Keeps the helper future-proof against an id-scheme change.
      expect(wordAudioPath({ id: 'X-99' })).toBe('audio/words/X-99.mp3');
    });
  });

  describe('REGRESSION: every minted word has a derivable path', () => {
    it('story-4 new words from the screenshot all build a valid flat path', () => {
      // The three words flagged 'new' in stories/story_4.json: W00021/22/23.
      // Their audio files exist on disk at audio/words/W000{21,22,23}.mp3
      // (post-2026-04-29 migration).
      for (const id of ['W00021', 'W00022', 'W00023']) {
        expect(wordAudioPath({ id })).toBe(`audio/words/${id}.mp3`);
      }
    });

    it('a word from a much later story has the same flat-path shape', () => {
      // Audio for W00099 lives at audio/words/W00099.mp3, NOT
      // audio/story_30/w_W00099.mp3 (the legacy layout).
      expect(wordAudioPath({ id: 'W00099' })).toBe('audio/words/W00099.mp3');
    });
  });
});
