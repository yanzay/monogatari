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
  tickListeningMinting,
  sentenceListeningReady,
  isDue,
  buildQueue,
  newCard,
  applyGrade,
  GRADES,
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

    it('buildQueue surfaces every minted card as a New entry', () => {
      // Since 2026-04-29 there is no `maxNew` cap; the user has already
      // opted into these words by reading the story they came from.
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      const q = buildQueue(srs, {
        now: NOW,
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

  describe('listening cards — mintCardsForStory never mints them (deferred to tickListeningMinting)', () => {
    /** Decorate the test story with sentence-audio paths the way
     *  decorateWithAudioPaths does at runtime. */
    function withAudio(story: Story): Story {
      return {
        ...story,
        sentences: story.sentences.map((s, i) => ({
          ...s,
          audio: s.audio ?? `audio/story_${story.story_id}/s${i}.mp3`,
        })),
      };
    }

    it('mints NO listening cards even when sentences have audio', () => {
      // Listening cards are deferred until all words in the sentence
      // are mature. mintCardsForStory is now reading-only.
      const story = withAudio(tenWordStory());
      const srs = mintCardsForStory(story, {}, NOW);
      const listeningIds = Object.keys(srs).filter((k) => k.startsWith('L:'));
      expect(listeningIds).toEqual([]);
      // Only the word/reading cards should be present.
      expect(Object.keys(srs).length).toBe(story.new_words.length);
    });

    it('mints NO listening cards even when sentences lack audio', () => {
      const story = tenWordStory();
      const srs = mintCardsForStory(story, {}, NOW);
      const listeningIds = Object.keys(srs).filter((k) => k.startsWith('L:'));
      expect(listeningIds).toEqual([]);
    });

    it('all minted cards have kind="reading"', () => {
      const story = withAudio(tenWordStory());
      const srs = mintCardsForStory(story, {}, NOW);
      for (const card of Object.values(srs)) {
        expect(card.kind).toBe('reading');
      }
    });
  });
});

// ── tickListeningMinting (deferred, mature-gated mint) ─────────────────────
// All required symbols imported at the top of this file.

/** Make a card mature by fast-forwarding through FSRS grading enough
 *  times to push the interval above MATURE_THRESHOLD_DAYS (21 days in
 *  the current srs.ts constant). We do 5 × Easy starting from NOW and
 *  advancing the clock by scheduled_days each time — a realistic path
 *  to maturity. */
function matureCard(wid: string, storyId: number, sentIdx: number): Card {
  let c = newCard({ word_id: wid, story_id: storyId, context_sentence_idx: sentIdx, kind: 'reading', now: NOW });
  let clock = NOW;
  for (let i = 0; i < 5; i++) {
    clock = new Date(clock.getTime() + Math.max(1, c.scheduled_days) * 86_400_000);
    const r = applyGrade(c, GRADES.EASY, clock);
    c = r.card;
  }
  return c;
}

describe('tickListeningMinting', () => {
  function withAudio(story: Story): Story {
    return {
      ...story,
      sentences: story.sentences.map((s, i) => ({
        ...s,
        audio: s.audio ?? `audio/story_${story.story_id}/s${i}.mp3`,
      })),
    };
  }

  function allReadingMature(story: Story, now: Date = NOW): Record<string, Card> {
    const srs: Record<string, Card> = {};
    for (const wid of story.new_words) {
      srs[wid] = matureCard(wid, story.story_id, 0);
    }
    return srs;
  }

  it('returns the same SRS reference when nothing changes (no-op path)', () => {
    const story = tenWordStory(); // no audio → nothing to mint
    const srs = allReadingMature(story);
    const result = tickListeningMinting(story, srs);
    expect(result).toBe(srs); // reference equality = no copy made
  });

  it('mints listening cards for sentences whose words are all mature', () => {
    const story = withAudio(tenWordStory());
    const srs = allReadingMature(story);
    const result = tickListeningMinting(story, srs, NOW);
    const listeningIds = Object.keys(result).filter((k) => k.startsWith('L:'));
    expect(listeningIds.sort()).toEqual(['L:4:0', 'L:4:1', 'L:4:2']);
  });

  it('minted listening cards have kind="listening" and correct metadata', () => {
    const story = withAudio(tenWordStory());
    const srs = allReadingMature(story);
    // Pass NOW explicitly so the new cards are due at NOW (not real clock).
    const result = tickListeningMinting(story, srs, NOW);
    for (let i = 0; i < 3; i++) {
      const card = result[`L:4:${i}`];
      expect(card.kind).toBe('listening');
      expect(card.context_story).toBe(4);
      expect(card.context_sentence_idx).toBe(i);
      expect(isDue(card, NOW)).toBe(true);
    }
  });

  it('does NOT mint listening cards when any word in the sentence is not mature', () => {
    const story = withAudio(tenWordStory());
    // Make all words reading-new (never reviewed).
    const srs: Record<string, Card> = {};
    for (const wid of story.new_words) {
      srs[wid] = newCard({ word_id: wid, story_id: 4, context_sentence_idx: 0, kind: 'reading', now: NOW });
    }
    const result = tickListeningMinting(story, srs);
    expect(result).toBe(srs); // no change
    expect(Object.keys(result).filter((k) => k.startsWith('L:'))).toEqual([]);
  });

  it('does NOT mint listening cards for sentences without audio', () => {
    const story = tenWordStory(); // no audio fields
    const srs = allReadingMature(story);
    const result = tickListeningMinting(story, srs);
    expect(result).toBe(srs);
    expect(Object.keys(result).filter((k) => k.startsWith('L:'))).toEqual([]);
  });

  it('is idempotent: a second tick does not duplicate or overwrite existing cards', () => {
    const story = withAudio(tenWordStory());
    const srs = allReadingMature(story);
    const first = tickListeningMinting(story, srs, NOW);
    const later = new Date(NOW.getTime() + 3_600_000);
    const second = tickListeningMinting(story, first, later);
    // Reference equality: second tick should be a no-op (all cards already present).
    expect(second).toBe(first);
    // Existing card `due` not bumped.
    for (const id of Object.keys(first).filter((k) => k.startsWith('L:'))) {
      expect(second[id].due).toBe(first[id].due);
    }
  });
});
