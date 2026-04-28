import { describe, it, expect, beforeEach } from 'vitest';
import { popup } from '../../../src/lib/state/popup.svelte';
import type { Sentence, Token } from '../../../src/lib/data/types';

const tok: Token = { t: '猫', r: 'ねこ', word_id: 'W00001', role: 'content' };
const sent: Sentence = {
  idx: 0,
  tokens: [tok],
  gloss_en: 'A cat.',
  audio: 'audio/story_1/s0.mp3',
};

describe('popup controller', () => {
  beforeEach(() => popup.close());

  it('starts closed', () => {
    expect(popup.current.kind).toBeNull();
  });

  describe('openWord', () => {
    it('opens a word popup with id and tok', () => {
      popup.openWord('W00001', tok);
      expect(popup.current.kind).toBe('word');
      expect(popup.current.wordId).toBe('W00001');
      // Svelte 5 wraps state in a proxy; we want value equality, not identity.
      expect(popup.current.tok).toStrictEqual(tok);
    });

    it('accepts null tok and stores it as undefined', () => {
      popup.openWord('W00002', null);
      expect(popup.current.kind).toBe('word');
      expect(popup.current.wordId).toBe('W00002');
      expect(popup.current.tok).toBeUndefined();
    });

    it('accepts no tok argument at all', () => {
      popup.openWord('W00003');
      expect(popup.current.kind).toBe('word');
      expect(popup.current.tok).toBeUndefined();
    });

    it('replaces a prior open popup of any kind', () => {
      popup.openGrammar('G001');
      popup.openWord('W00099', tok);
      expect(popup.current.kind).toBe('word');
      expect(popup.current.grammarId).toBeUndefined();
      expect(popup.current.wordId).toBe('W00099');
    });
  });

  describe('openGrammar', () => {
    it('opens a grammar popup', () => {
      popup.openGrammar('G001_wa_topic');
      expect(popup.current.kind).toBe('grammar');
      expect(popup.current.grammarId).toBe('G001_wa_topic');
    });

    it('clears any prior word context', () => {
      popup.openWord('W00001', tok);
      popup.openGrammar('G002');
      expect(popup.current.kind).toBe('grammar');
      expect(popup.current.wordId).toBeUndefined();
      expect(popup.current.tok).toBeUndefined();
    });
  });

  describe('openSentence', () => {
    it('opens a sentence popup with all three coordinates', () => {
      popup.openSentence(7, 3, sent);
      expect(popup.current.kind).toBe('sentence');
      expect(popup.current.sentence?.story_id).toBe(7);
      expect(popup.current.sentence?.sentence_idx).toBe(3);
      expect(popup.current.sentence?.data).toStrictEqual(sent);
    });

    it('clears word/grammar fields when opening a sentence', () => {
      popup.openWord('W00001', tok);
      popup.openSentence(1, 0, sent);
      expect(popup.current.kind).toBe('sentence');
      expect(popup.current.wordId).toBeUndefined();
      expect(popup.current.grammarId).toBeUndefined();
    });
  });

  describe('close', () => {
    it('returns kind to null and drops all payloads', () => {
      popup.openWord('W00001', tok);
      popup.close();
      expect(popup.current.kind).toBeNull();
      expect(popup.current.wordId).toBeUndefined();
      expect(popup.current.tok).toBeUndefined();
      expect(popup.current.grammarId).toBeUndefined();
      expect(popup.current.sentence).toBeUndefined();
    });

    it('is idempotent — close on closed is fine', () => {
      popup.close();
      popup.close();
      expect(popup.current.kind).toBeNull();
    });
  });
});
