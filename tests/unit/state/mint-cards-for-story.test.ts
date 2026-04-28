/**
 * Regression test for the "Save for review" flow.
 *
 * BUG (2026-04-28): pressing the read-view's "I've read this — save new
 * words for review" button minted all of the story's new_words as fresh
 * SRS cards but pushed each card's `due` field forward by
 * `dribbleOffset(i)` — 0, 90s, 180s, … — so only the very first new
 * card was actually due immediately. The read-view's "N due word(s)
 * here — review now" CTA and the layout's review-tab badge both filter
 * by `isDue(card, now)`, so a freshly-saved 10-word story showed only
 * "1 due word here" and "Review 1" in the menu. Confusing.
 *
 * The right behavior: directly after pressing save, every new word
 * minted from the story should be due NOW. Ordering across the
 * resulting review session is buildQueue's job (it already sorts new
 * cards stably by word_id), not the responsibility of the `due` field.
 *
 * This test pins the invariant at the point of minting via the pure
 * helper `mintCardsForStory` extracted from the read view. If the
 * dribble logic regresses, this test fails.
 */
import { describe, it, expect } from 'vitest';
import {
  mintCardsForStory,
  isDue,
  buildQueue,
} from '../../../src/lib/state/srs';
import type { Story } from '../../../src/lib/data/types';
import type { Card } from '../../../src/lib/state/types';

const NOW = new Date('2026-04-28T23:55:00.000Z');

function tenWordStory(): Story {
  // Mirrors the shape of a real story_4-ish artifact: 10 unique words
  // distributed across 5 sentences, all flagged as new.
  const wordIds = Array.from({ length: 10 }, (_, i) => `W${String(i + 1).padStart(5, '0')}`);
  return {
    story_id: 4,
    title: { jp: '鍵', en: 'The Key' },
    new_words: wordIds,
    new_grammar: [],
    sentences: [
      {
        idx: 0,
        gloss_en: 'morning, I see a friend on the road.',
        tokens: [
          { t: '朝', word_id: wordIds[1], role: 'content' },
          { t: '、', role: 'punct' },
          { t: '私', word_id: wordIds[2], role: 'content' },
          { t: 'は', role: 'particle' },
          { t: '道', word_id: wordIds[3], role: 'content' },
          { t: 'で', role: 'particle' },
          { t: '友達', word_id: wordIds[4], role: 'content' },
          { t: 'を', role: 'particle' },
          { t: '見ます', word_id: wordIds[5], role: 'content' },
          { t: '。', role: 'punct' },
        ],
      },
      {
        idx: 1,
        gloss_en: 'I hold a small key in my hand.',
        tokens: [
          { t: '私', word_id: wordIds[2], role: 'content' },
          { t: 'は', role: 'particle' },
          { t: '手', word_id: wordIds[6], role: 'content' },
          { t: 'に', role: 'particle' },
          { t: '小さい', word_id: wordIds[7], role: 'content' },
          { t: '鍵', word_id: wordIds[0], role: 'content' },
          { t: 'を', role: 'particle' },
          { t: '持ちます', word_id: wordIds[8], role: 'content' },
          { t: '。', role: 'punct' },
        ],
      },
      {
        idx: 2,
        gloss_en: 'I hand the key to the friend.',
        tokens: [
          { t: '私', word_id: wordIds[2], role: 'content' },
          { t: 'は', role: 'particle' },
          { t: '鍵', word_id: wordIds[0], role: 'content' },
          { t: 'を', role: 'particle' },
          { t: '友達', word_id: wordIds[4], role: 'content' },
          { t: 'に', role: 'particle' },
          { t: '渡します', word_id: wordIds[9], role: 'content' },
          { t: '。', role: 'punct' },
        ],
      },
    ],
  };
}

describe('mintCardsForStory', () => {
  it('mints one card per unique new_word in the story', () => {
    const story = tenWordStory();
    const srs = mintCardsForStory(story, {}, NOW);
    expect(Object.keys(srs).sort()).toEqual([...story.new_words].sort());
  });

  it('does NOT overwrite an existing card for the same word_id', () => {
    const story = tenWordStory();
    const existing: Card = {
      word_id: story.new_words[0],
      first_learned_story: 1,
      context_story: 1,
      context_sentence_idx: 0,
      due: '2099-01-01T00:00:00.000Z',
      stability: 99,
      difficulty: 1,
      elapsed_days: 0,
      scheduled_days: 365,
      learning_steps: 0,
      reps: 50,
      lapses: 0,
      state: 2 as Card['state'],
      status: 'mature',
    };
    const srs = mintCardsForStory(story, { [existing.word_id]: existing }, NOW);
    // Existing card preserved verbatim; the rest are minted.
    expect(srs[existing.word_id]).toEqual(existing);
    expect(srs[existing.word_id].stability).toBe(99);
    expect(Object.keys(srs)).toHaveLength(story.new_words.length);
  });

  it('attaches a context_sentence_idx pointing at the FIRST sentence containing the word', () => {
    const story = tenWordStory();
    const srs = mintCardsForStory(story, {}, NOW);
    // word index 0 = '鍵' first appears in sentence 1 (sentence 2 also uses it).
    expect(srs[story.new_words[0]].context_sentence_idx).toBe(1);
    // word index 1 = '朝' first appears in sentence 0.
    expect(srs[story.new_words[1]].context_sentence_idx).toBe(0);
    // word index 9 = '渡します' first appears in sentence 2.
    expect(srs[story.new_words[9]].context_sentence_idx).toBe(2);
  });

  it('records context_story and first_learned_story as the source story id', () => {
    const story = tenWordStory();
    const srs = mintCardsForStory(story, {}, NOW);
    for (const card of Object.values(srs)) {
      expect(card.first_learned_story).toBe(story.story_id);
      expect(card.context_story).toBe(story.story_id);
    }
  });

  describe('REGRESSION: every minted card is due immediately', () => {
    it('isDue(card, now) returns true for ALL minted cards (not just the first)', () => {
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      const dueNow = Object.values(srs).filter((c) => isDue(c, NOW));
      expect(dueNow.length).toBe(story.new_words.length);
      // Spell out the original failure mode: under the buggy dribble
      // logic only the first-minted card was due now.
      expect(dueNow.length).not.toBe(1);
    });

    it('the layout-style "due count" predicate sees every minted card', () => {
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      // Replicate +layout.svelte's dueCount filter shape exactly so any
      // future drift between the two predicates is caught here.
      const dueCount = Object.values(srs).filter((c) => {
        if (!c.due) return true;
        const t = new Date(c.due).getTime();
        return !Number.isFinite(t) || t <= NOW.getTime();
      }).length;
      expect(dueCount).toBe(story.new_words.length);
    });

    it('the read-view "N due word here" CTA sees every minted card', () => {
      // Replicate +page.svelte::dueInThisStory: union of all word_ids in
      // the story's tokens, intersected with srs, filtered by isDue.
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      const idsInStory = new Set<string>();
      for (const sent of story.sentences) {
        for (const tok of sent.tokens) {
          if (tok.word_id) idsInStory.add(tok.word_id);
        }
      }
      let dueInStory = 0;
      for (const id of idsInStory) {
        const card = srs[id];
        if (card && isDue(card, NOW)) dueInStory += 1;
      }
      // 9 of the 10 minted ids appear in the sentence tokens above; the
      // 10th (story.new_words[0] = '鍵') also appears (sentence 1 + 2),
      // so all 10 should be counted as due in this story.
      expect(dueInStory).toBe(story.new_words.length);
    });

    it('buildQueue surfaces every minted card as a New entry (subject to caps)', () => {
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      const q = buildQueue(srs, {
        now: NOW,
        maxNew: 100,
        maxReviews: 100,
        newPerReview: 0,
      });
      expect(q).toHaveLength(story.new_words.length);
    });
  });

  describe('idempotency / repeat call', () => {
    it('a second mint pass over the same story is a no-op (existing cards preserved)', () => {
      const story = tenWordStory();
      const first = mintCardsForStory(story, {}, NOW);
      const later = new Date(NOW.getTime() + 60 * 60 * 1000);
      const second = mintCardsForStory(story, first, later);
      // Same set of ids, and each card's `due` is the original (not bumped forward).
      expect(Object.keys(second).sort()).toEqual(Object.keys(first).sort());
      for (const id of Object.keys(first)) {
        expect(second[id].due).toBe(first[id].due);
      }
    });
  });
});
