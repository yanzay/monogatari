/**
 * Regression tests for the word-audio path helper.
 *
 * BUG (2026-04-29): the WordPopup's "▶ play word" button never
 * appeared because the +layout.svelte invocation passed `story={null}`
 * and the popup derived audioSrc from `story?.word_audio?.[id]`. Empty.
 *
 * Fix: derive audio from the word itself, since every minted word has
 * a file at `audio/story_<first_story>/w_<id>.mp3` written by the
 * audio_builder. This helper is the source-of-truth for that path
 * everywhere in the UI; tests pin its behaviour against the variety
 * of `first_story` shapes that have shipped in vocab_state.json.
 */
import { describe, it, expect } from 'vitest';
import { wordAudioPath } from '../../../src/lib/util/word-audio';

describe('wordAudioPath', () => {
  it('returns null for null', () => {
    expect(wordAudioPath(null)).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(wordAudioPath(undefined)).toBeNull();
  });

  it('returns null when id is missing', () => {
    expect(wordAudioPath({ first_story: 4 })).toBeNull();
  });

  it('returns null when first_story is missing', () => {
    expect(wordAudioPath({ id: 'W00001' })).toBeNull();
  });

  it('returns null when first_story is null', () => {
    expect(wordAudioPath({ id: 'W00001', first_story: null as unknown as number })).toBeNull();
  });

  describe('numeric first_story', () => {
    it('builds a path from id + integer first_story', () => {
      expect(wordAudioPath({ id: 'W00021', first_story: 4 })).toBe(
        'audio/story_4/w_W00021.mp3',
      );
    });

    it('handles two-digit story numbers', () => {
      expect(wordAudioPath({ id: 'W00099', first_story: 17 })).toBe(
        'audio/story_17/w_W00099.mp3',
      );
    });

    it('rejects zero and negative integers', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: 0 })).toBeNull();
      expect(wordAudioPath({ id: 'W00001', first_story: -3 })).toBeNull();
    });

    it('rejects NaN', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: NaN })).toBeNull();
    });

    it('rejects Infinity', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: Infinity })).toBeNull();
    });
  });

  describe('string first_story (vocab_state.json shape)', () => {
    it('extracts the trailing integer from "story_<n>"', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: 'story_4' })).toBe(
        'audio/story_4/w_W00001.mp3',
      );
    });

    it('handles two-digit story IDs', () => {
      expect(wordAudioPath({ id: 'W00050', first_story: 'story_17' })).toBe(
        'audio/story_17/w_W00050.mp3',
      );
    });

    it('returns null for a string with no trailing integer', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: 'story_unknown' })).toBeNull();
    });

    it('returns null for an empty string', () => {
      expect(wordAudioPath({ id: 'W00001', first_story: '' })).toBeNull();
    });

    it('extracts the LAST integer if string contains multiple', () => {
      // Defensive — a path-like value gets the final segment.
      expect(wordAudioPath({ id: 'W00001', first_story: 'story_42' })).toBe(
        'audio/story_42/w_W00001.mp3',
      );
    });
  });

  describe('REGRESSION: every minted word has a derivable path', () => {
    it('story-4 new words from the screenshot all build a valid path', () => {
      // The three words flagged 'new' in stories/story_4.json: W00021/22/23.
      // Their audio files exist on disk at audio/story_4/w_W000{21,22,23}.mp3.
      for (const id of ['W00021', 'W00022', 'W00023']) {
        expect(wordAudioPath({ id, first_story: 4 })).toBe(
          `audio/story_4/w_${id}.mp3`,
        );
        expect(wordAudioPath({ id, first_story: 'story_4' })).toBe(
          `audio/story_4/w_${id}.mp3`,
        );
      }
    });
  });
});
