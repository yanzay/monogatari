/**
 * Tests for the LearnerStore class methods (the runes-backed instance
 * exported as `learner`). The pure sanitizeImported logic is covered
 * separately in learner.test.ts.
 *
 * `browser` is mocked false so save() / resetAll() are no-ops; we test
 * the synchronous in-memory behavior here. IDB calls are stubbed.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: false }));
vi.mock('idb-keyval', () => ({
  get: vi.fn(async () => undefined),
  set: vi.fn(async () => undefined),
  del: vi.fn(async () => undefined),
}));

import { learner } from '../../../src/lib/state/learner.svelte';
import type { Card, ReviewLogEntry } from '../../../src/lib/state/types';

const HISTORY_CAP = 500;

function makeCard(word_id = 'W00001', overrides: Partial<Card> = {}): Card {
  return {
    word_id,
    first_learned_story: 1,
    context_story: 1,
    context_sentence_idx: 0,
    due: '2026-04-28T00:00:00.000Z',
    stability: 1.5,
    difficulty: 5.0,
    elapsed_days: 0,
    scheduled_days: 1,
    learning_steps: 0,
    reps: 1,
    lapses: 0,
    state: 1 as Card['state'],
    status: 'learning',
    ...overrides,
  };
}

function makeEntry(word_id = 'W00001', i = 0): ReviewLogEntry {
  const before = makeCard(word_id, { reps: i });
  const after = makeCard(word_id, { reps: i + 1 });
  return {
    word_id,
    grade: 1,
    reviewed_at: new Date(2026, 3, 28, 12, 0, i).toISOString(),
    card_before: before,
    card_after: after,
  };
}

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

beforeEach(() => {
  // Reset to a known clean state between tests. We use replace() so the
  // store's reactive proxy is preserved.
  learner.replace({
    version: 3,
    current_story: 1,
    last_opened: new Date().toISOString(),
    srs: {},
    story_progress: {},
    prefs: {
      show_gloss_by_default: false,
      audio_on_review_reveal: true,
      audio_listen_first: false,
      theme: 'auto',
      target_retention: 0.9,
      // daily_max_new removed 2026-04-29; daily_max_reviews defaults to null (no cap).
      daily_max_reviews: null,
      new_per_review: 4,
    },
    history: [],
    daily: { date: todayLocal(), reviewed: 0 },
  });
});

describe('LearnerStore', () => {
  describe('initial state', () => {
    it('starts with version 3 (current FSRS schema)', () => {
      expect(learner.state.version).toBe(3);
    });

    it('starts on story 1', () => {
      expect(learner.state.current_story).toBe(1);
    });

    it('starts with empty srs and history', () => {
      expect(learner.state.srs).toEqual({});
      expect(learner.state.history).toEqual([]);
    });
  });

  describe('rolloverDailyIfNeeded', () => {
    it('does nothing when date matches today', () => {
      learner.state.daily = { date: todayLocal(), reviewed: 5 };
      learner.rolloverDailyIfNeeded();
      expect(learner.state.daily.reviewed).toBe(5);
    });

    it('resets reviewed when date is stale', () => {
      learner.state.daily = { date: '2000-01-01', reviewed: 99 };
      learner.rolloverDailyIfNeeded();
      expect(learner.state.daily.reviewed).toBe(0);
      expect(learner.state.daily.date).toBe(todayLocal());
    });

    it('is idempotent — second call after rollover is a no-op', () => {
      learner.state.daily = { date: '1999-12-31', reviewed: 5 };
      learner.rolloverDailyIfNeeded();
      const after = { ...learner.state.daily };
      learner.rolloverDailyIfNeeded();
      expect(learner.state.daily).toEqual(after);
    });
  });

  describe('pushHistory', () => {
    it('appends an entry and increments daily.reviewed', () => {
      learner.pushHistory(makeEntry('W00001', 0));
      expect(learner.state.history).toHaveLength(1);
      expect(learner.state.daily.reviewed).toBe(1);
    });

    it('appends in order — last push is at the end', () => {
      learner.pushHistory(makeEntry('W00001', 0));
      learner.pushHistory(makeEntry('W00002', 0));
      learner.pushHistory(makeEntry('W00003', 0));
      expect(learner.state.history.map((e) => e.word_id)).toEqual([
        'W00001',
        'W00002',
        'W00003',
      ]);
      expect(learner.state.daily.reviewed).toBe(3);
    });

    it('caps history at HISTORY_CAP entries (drops oldest)', () => {
      for (let i = 0; i < HISTORY_CAP + 25; i++) {
        learner.pushHistory(makeEntry(`W${String(i).padStart(5, '0')}`, i));
      }
      expect(learner.state.history).toHaveLength(HISTORY_CAP);
      // First surviving entry should be the 25th (since we dropped 25 oldest).
      expect(learner.state.history[0].word_id).toBe('W00025');
      // Last surviving entry is the most recent push.
      const last = learner.state.history[learner.state.history.length - 1];
      expect(last.word_id).toBe(`W${String(HISTORY_CAP + 24).padStart(5, '0')}`);
    });

    it('still increments daily.reviewed when capping', () => {
      for (let i = 0; i < HISTORY_CAP + 5; i++) {
        learner.pushHistory(makeEntry(`W${i}`, i));
      }
      // The reviewed counter is not capped — counts every push.
      expect(learner.state.daily.reviewed).toBe(HISTORY_CAP + 5);
    });
  });

  describe('popHistory', () => {
    it('returns null on empty history', () => {
      expect(learner.popHistory()).toBeNull();
    });

    it('removes the most recent entry and returns it', () => {
      const e1 = makeEntry('A', 0);
      const e2 = makeEntry('B', 0);
      learner.pushHistory(e1);
      learner.pushHistory(e2);
      const popped = learner.popHistory();
      expect(popped?.word_id).toBe('B');
      expect(learner.state.history.map((e) => e.word_id)).toEqual(['A']);
    });

    it('restores the card_before snapshot into srs[word_id]', () => {
      const before = makeCard('W00001', { reps: 7, stability: 9.5 });
      const after = makeCard('W00001', { reps: 8, stability: 12.5 });
      // Pre-existing post-review card in srs; pop should overwrite it
      // with the pre-review snapshot.
      learner.state.srs.W00001 = after;
      learner.pushHistory({
        word_id: 'W00001',
        grade: 1,
        reviewed_at: new Date().toISOString(),
        card_before: before,
        card_after: after,
      });
      learner.popHistory();
      expect(learner.state.srs.W00001.reps).toBe(7);
      expect(learner.state.srs.W00001.stability).toBe(9.5);
    });

    it('decrements daily.reviewed but never below zero', () => {
      learner.pushHistory(makeEntry('W00001', 0));
      expect(learner.state.daily.reviewed).toBe(1);
      learner.popHistory();
      expect(learner.state.daily.reviewed).toBe(0);
      // Pop again on empty history should NOT take counter negative.
      learner.popHistory();
      expect(learner.state.daily.reviewed).toBe(0);
    });
  });

  describe('replace', () => {
    it('swaps the entire state object', () => {
      learner.replace({
        ...learner.state,
        current_story: 42,
      });
      expect(learner.state.current_story).toBe(42);
    });
  });

  describe('exportJSON', () => {
    it('returns valid JSON that round-trips through JSON.parse', () => {
      learner.state.current_story = 9;
      learner.state.srs.W00001 = makeCard('W00001');
      const json = learner.exportJSON();
      const parsed = JSON.parse(json);
      expect(parsed.current_story).toBe(9);
      expect(parsed.srs.W00001.word_id).toBe('W00001');
      expect(parsed.version).toBe(3);
    });

    it('formats with 2-space indentation', () => {
      const json = learner.exportJSON();
      expect(json).toContain('\n  ');
    });
  });

  describe('resetAll', () => {
    it('clears srs, history, story_progress back to defaults', async () => {
      learner.state.srs.W00001 = makeCard('W00001');
      learner.state.history.push(makeEntry('W00001', 0));
      learner.state.story_progress['1'] = { completed: true };
      learner.state.current_story = 7;
      await learner.resetAll();
      expect(learner.state.srs).toEqual({});
      expect(learner.state.history).toEqual([]);
      expect(learner.state.story_progress).toEqual({});
      expect(learner.state.current_story).toBe(1);
      expect(learner.state.version).toBe(3);
    });
  });

  describe('save (browser=false short-circuit)', () => {
    it('returns without throwing in the SSR/test environment', () => {
      expect(() => learner.save()).not.toThrow();
    });
  });
});
