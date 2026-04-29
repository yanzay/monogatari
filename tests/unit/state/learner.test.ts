import { describe, it, expect } from 'vitest';
import { sanitizeImported } from '../../../src/lib/state/learner.svelte';
import type { Card, ReviewLogEntry } from '../../../src/lib/state/types';

const CURRENT_VERSION = 3;
const HISTORY_CAP = 500;
const DEFAULT_TARGET_RETENTION = 0.9;

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function makeCard(overrides: Partial<Card> = {}): Card {
  return {
    word_id: 'W00001',
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

function makeHistoryEntry(overrides: Partial<ReviewLogEntry> = {}): ReviewLogEntry {
  const before = makeCard();
  const after = makeCard({ reps: 2 });
  return {
    word_id: 'W00001',
    grade: 1,
    reviewed_at: '2026-04-28T12:00:00.000Z',
    card_before: before,
    card_after: after,
    ...overrides,
  };
}

describe('sanitizeImported', () => {
  describe('input rejection', () => {
    it('throws on null', () => {
      expect(() => sanitizeImported(null)).toThrow(/not an object/);
    });

    it('throws on undefined', () => {
      expect(() => sanitizeImported(undefined)).toThrow(/not an object/);
    });

    it('throws on a string', () => {
      expect(() => sanitizeImported('garbage')).toThrow(/not an object/);
    });

    it('throws on a number', () => {
      expect(() => sanitizeImported(42)).toThrow(/not an object/);
    });

    it('throws on a boolean', () => {
      expect(() => sanitizeImported(true)).toThrow(/not an object/);
    });

    it('accepts an empty object — returns defaults with current version', () => {
      const out = sanitizeImported({});
      expect(out.version).toBe(CURRENT_VERSION);
      expect(out.current_story).toBe(1);
      expect(out.srs).toEqual({});
      expect(out.history).toEqual([]);
      expect(out.story_progress).toEqual({});
      expect(out.prefs.target_retention).toBe(DEFAULT_TARGET_RETENTION);
    });
  });

  describe('version handling', () => {
    it('forces version to CURRENT_VERSION on output, regardless of input', () => {
      expect(sanitizeImported({ version: 1 }).version).toBe(CURRENT_VERSION);
      expect(sanitizeImported({ version: 2 }).version).toBe(CURRENT_VERSION);
      expect(sanitizeImported({ version: 99 }).version).toBe(CURRENT_VERSION);
    });

    it('drops srs when version mismatches (no migration)', () => {
      const card = makeCard();
      const out = sanitizeImported({
        version: 2,
        srs: { W00001: card },
      });
      expect(out.srs).toEqual({});
    });

    it('drops history when version mismatches', () => {
      const out = sanitizeImported({
        version: 2,
        history: [makeHistoryEntry()],
      });
      expect(out.history).toEqual([]);
    });

    it('keeps srs when version matches CURRENT_VERSION', () => {
      const card = makeCard();
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: card },
      });
      expect(out.srs.W00001).toBeDefined();
      expect(out.srs.W00001.stability).toBe(1.5);
    });

    it('keeps history when version matches', () => {
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        history: [makeHistoryEntry()],
      });
      expect(out.history).toHaveLength(1);
    });

    it('drops srs when version field is missing entirely (treated as mismatch)', () => {
      const card = makeCard();
      const out = sanitizeImported({ srs: { W00001: card } });
      expect(out.srs).toEqual({});
    });
  });

  describe('srs sanitization', () => {
    it('rewrites word_id from the dict key, not the card field', () => {
      const card = makeCard({ word_id: 'OLD' });
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W99999: card },
      });
      expect(out.srs.W99999.word_id).toBe('W99999');
    });

    it('drops cards missing the stability field', () => {
      const broken: any = { ...makeCard() };
      delete broken.stability;
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: broken },
      });
      expect(out.srs.W00001).toBeUndefined();
    });

    it('drops cards missing the difficulty field', () => {
      const broken: any = { ...makeCard() };
      delete broken.difficulty;
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: broken },
      });
      expect(out.srs.W00001).toBeUndefined();
    });

    it('drops cards missing the due field', () => {
      const broken: any = { ...makeCard() };
      delete broken.due;
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: broken },
      });
      expect(out.srs.W00001).toBeUndefined();
    });

    it('drops cards where stability is the wrong type', () => {
      const broken = { ...makeCard(), stability: 'oops' as unknown as number };
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: broken },
      });
      expect(out.srs.W00001).toBeUndefined();
    });

    it('drops null/undefined card values', () => {
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: { W00001: null, W00002: undefined, W00003: makeCard({ word_id: 'W00003' }) },
      });
      expect(out.srs.W00001).toBeUndefined();
      expect(out.srs.W00002).toBeUndefined();
      expect(out.srs.W00003).toBeDefined();
    });

    it('keeps multiple valid cards', () => {
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        srs: {
          W00001: makeCard(),
          W00002: makeCard({ stability: 3.7 }),
          W00003: makeCard({ stability: 0.5 }),
        },
      });
      expect(Object.keys(out.srs)).toEqual(['W00001', 'W00002', 'W00003']);
    });
  });

  describe('history sanitization', () => {
    it('rejects entries missing required fields', () => {
      const valid = makeHistoryEntry();
      const invalid: any = { word_id: 'W00001' }; // missing grade, etc.
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        history: [valid, invalid],
      });
      expect(out.history).toHaveLength(1);
    });

    it('caps history at HISTORY_CAP, keeping the most recent entries', () => {
      const entries = Array.from({ length: HISTORY_CAP + 50 }, (_, i) =>
        makeHistoryEntry({ word_id: `W${String(i).padStart(5, '0')}` }),
      );
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        history: entries,
      });
      expect(out.history).toHaveLength(HISTORY_CAP);
      // The kept slice should be the LAST 500.
      expect(out.history[0].word_id).toBe(entries[50].word_id);
      expect(out.history[HISTORY_CAP - 1].word_id).toBe(entries[entries.length - 1].word_id);
    });

    it('returns empty array when history is not an array', () => {
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        history: 'not an array' as unknown as ReviewLogEntry[],
      });
      expect(out.history).toEqual([]);
    });
  });

  describe('daily counters', () => {
    it("keeps daily counters when date matches today's local date", () => {
      const out = sanitizeImported({
        daily: { date: todayLocal(), reviewed: 7 },
      });
      expect(out.daily.reviewed).toBe(7);
      expect(out.daily.date).toBe(todayLocal());
    });

    it('resets daily counters when date is in the past', () => {
      const out = sanitizeImported({
        daily: { date: '2000-01-01', reviewed: 99 },
      });
      expect(out.daily.reviewed).toBe(0);
      expect(out.daily.date).toBe(todayLocal());
    });

    it('coerces non-numeric reviewed to 0', () => {
      const out = sanitizeImported({
        daily: {
          date: todayLocal(),
          reviewed: 'lots' as unknown as number,
        },
      });
      expect(out.daily.reviewed).toBe(0);
    });

    it('silently drops the legacy new_introduced field on import', () => {
      // The pref it served (daily_max_new) was removed; the counter has
      // no consumer and shouldn't survive a sanitize pass.
      const out = sanitizeImported({
        daily: {
          date: todayLocal(),
          reviewed: 5,
          new_introduced: 3,
        } as unknown as Record<string, unknown>,
      });
      expect(out.daily.reviewed).toBe(5);
      expect(
        (out.daily as unknown as Record<string, unknown>).new_introduced,
      ).toBeUndefined();
    });

    it('uses defaults when daily field is missing', () => {
      const out = sanitizeImported({});
      expect(out.daily.date).toBe(todayLocal());
      expect(out.daily.reviewed).toBe(0);
    });
  });

  describe('story_progress', () => {
    it('keeps only entries explicitly marked completed=true', () => {
      const out = sanitizeImported({
        story_progress: {
          '1': { completed: true },
          '2': { completed: false },
          '3': { completed: true },
          '4': {},
        } as unknown as Record<string, { completed: boolean }>,
      });
      expect(Object.keys(out.story_progress).sort()).toEqual(['1', '3']);
      expect(out.story_progress['1']).toEqual({ completed: true });
    });

    it('returns empty object when story_progress is missing', () => {
      const out = sanitizeImported({});
      expect(out.story_progress).toEqual({});
    });

    it('drops null entries silently', () => {
      const out = sanitizeImported({
        story_progress: { '1': null, '2': { completed: true } } as unknown as Record<
          string,
          { completed: boolean }
        >,
      });
      expect(out.story_progress).toEqual({ '2': { completed: true } });
    });
  });

  describe('prefs', () => {
    it('coerces truthy values for show_gloss_by_default', () => {
      const out = sanitizeImported({
        prefs: {
          show_gloss_by_default: 'yes',
        },
      });
      expect(out.prefs.show_gloss_by_default).toBe(true);
    });

    it('silently drops removed pref keys (e.g. legacy audio_autoplay)', () => {
      const out = sanitizeImported({
        prefs: {
          audio_autoplay: true, // removed 2026-04-29
        },
      });
      expect((out.prefs as unknown as Record<string, unknown>).audio_autoplay).toBeUndefined();
    });

    it('preserves explicit false for audio_on_review_reveal', () => {
      const out = sanitizeImported({
        prefs: { audio_on_review_reveal: false },
      });
      expect(out.prefs.audio_on_review_reveal).toBe(false);
    });

    it('defaults audio_on_review_reveal to true when absent', () => {
      const out = sanitizeImported({ prefs: {} });
      expect(out.prefs.audio_on_review_reveal).toBe(true);
    });

    describe('audio_echo_on_grade (replaces retired audio_listen_first)', () => {
      it('defaults to "mature_only" when absent', () => {
        const out = sanitizeImported({ prefs: {} });
        expect(out.prefs.audio_echo_on_grade).toBe('mature_only');
      });

      it.each(['never', 'mature_only', 'always'] as const)(
        'preserves explicit %s',
        (policy) => {
          const out = sanitizeImported({ prefs: { audio_echo_on_grade: policy } });
          expect(out.prefs.audio_echo_on_grade).toBe(policy);
        },
      );

      it('rejects unknown policy strings (defaults to mature_only)', () => {
        const out = sanitizeImported({ prefs: { audio_echo_on_grade: 'often' } });
        expect(out.prefs.audio_echo_on_grade).toBe('mature_only');
      });

      it('migrates legacy audio_listen_first=true → "mature_only"', () => {
        // The retired toggle's spirit was "I want some sentence audio
        // exposure"; mature_only is the safe modernization.
        const out = sanitizeImported({ prefs: { audio_listen_first: true } });
        expect(out.prefs.audio_echo_on_grade).toBe('mature_only');
      });

      it('migrates legacy audio_listen_first=false → "never"', () => {
        const out = sanitizeImported({ prefs: { audio_listen_first: false } });
        expect(out.prefs.audio_echo_on_grade).toBe('never');
      });

      it('explicit new pref wins over legacy bool when both are present', () => {
        const out = sanitizeImported({
          prefs: { audio_listen_first: true, audio_echo_on_grade: 'never' },
        });
        expect(out.prefs.audio_echo_on_grade).toBe('never');
      });

      it('silently drops the legacy audio_listen_first field on import', () => {
        // The new pref is audio_echo_on_grade; the boolean should not
        // survive a sanitize pass.
        const out = sanitizeImported({ prefs: { audio_listen_first: true } });
        expect(
          (out.prefs as unknown as Record<string, unknown>).audio_listen_first,
        ).toBeUndefined();
      });
    });

    describe('listening_per_review (short-lived pref, now removed)', () => {
      // listening_per_review existed only on 2026-04-29. It was removed when
      // listening became a separate tab. The sanitizer silently drops it;
      // these tests verify the field does NOT appear on the imported prefs.
      it('is silently dropped and does not appear in imported prefs', () => {
        const out = sanitizeImported({ prefs: { listening_per_review: 4 } });
        expect(
          (out.prefs as unknown as Record<string, unknown>).listening_per_review,
        ).toBeUndefined();
      });

      it('does not appear in default prefs either', () => {
        const out = sanitizeImported({});
        expect(
          (out.prefs as unknown as Record<string, unknown>).listening_per_review,
        ).toBeUndefined();
      });
    });

    describe('theme', () => {
      it.each(['light', 'dark', 'auto'] as const)('accepts %s', (theme) => {
        const out = sanitizeImported({ prefs: { theme } });
        expect(out.prefs.theme).toBe(theme);
      });

      it('rejects unknown theme strings', () => {
        const out = sanitizeImported({ prefs: { theme: 'sepia' } });
        expect(out.prefs.theme).toBe('auto');
      });

      it('rejects non-string theme', () => {
        const out = sanitizeImported({ prefs: { theme: 5 } });
        expect(out.prefs.theme).toBe('auto');
      });
    });

    describe('target_retention', () => {
      it('accepts a value in range', () => {
        const out = sanitizeImported({ prefs: { target_retention: 0.85 } });
        expect(out.prefs.target_retention).toBe(0.85);
      });

      it('rejects values below 0.7', () => {
        const out = sanitizeImported({ prefs: { target_retention: 0.5 } });
        expect(out.prefs.target_retention).toBe(DEFAULT_TARGET_RETENTION);
      });

      it('rejects values above 0.99', () => {
        const out = sanitizeImported({ prefs: { target_retention: 0.999 } });
        expect(out.prefs.target_retention).toBe(DEFAULT_TARGET_RETENTION);
      });

      it('accepts the boundary 0.7', () => {
        const out = sanitizeImported({ prefs: { target_retention: 0.7 } });
        expect(out.prefs.target_retention).toBe(0.7);
      });

      it('accepts the boundary 0.99', () => {
        const out = sanitizeImported({ prefs: { target_retention: 0.99 } });
        expect(out.prefs.target_retention).toBe(0.99);
      });

      it('rejects non-numeric retention', () => {
        const out = sanitizeImported({ prefs: { target_retention: '0.9' } });
        expect(out.prefs.target_retention).toBe(DEFAULT_TARGET_RETENTION);
      });
    });

    describe('numeric quotas', () => {
      it('silently drops the legacy daily_max_new pref on import', () => {
        // Removed 2026-04-29 — see Prefs.daily_max_reviews docstring.
        const out = sanitizeImported({ prefs: { daily_max_new: 7 } });
        expect(
          (out.prefs as unknown as Record<string, unknown>).daily_max_new,
        ).toBeUndefined();
      });

      it('accepts a positive daily_max_reviews and floors it', () => {
        const out = sanitizeImported({ prefs: { daily_max_reviews: 150.5 } });
        expect(out.prefs.daily_max_reviews).toBe(150);
      });

      it('coerces zero daily_max_reviews to null (no-cap)', () => {
        // Zero would mean "I want zero reviews per day" — the user almost
        // certainly didn't mean that, so collapse to the no-cap default.
        const out = sanitizeImported({ prefs: { daily_max_reviews: 0 } });
        expect(out.prefs.daily_max_reviews).toBeNull();
      });

      it('coerces negative daily_max_reviews to null (no-cap)', () => {
        const out = sanitizeImported({ prefs: { daily_max_reviews: -1 } });
        expect(out.prefs.daily_max_reviews).toBeNull();
      });

      it('coerces non-numeric daily_max_reviews to null (no-cap)', () => {
        const out = sanitizeImported({
          prefs: { daily_max_reviews: 'lots' as unknown as number },
        });
        expect(out.prefs.daily_max_reviews).toBeNull();
      });

      it('floors and accepts new_per_review', () => {
        const out = sanitizeImported({ prefs: { new_per_review: 6.7 } });
        expect(out.prefs.new_per_review).toBe(6);
      });

      it('rejects non-number new_per_review (defaults to 4)', () => {
        const out = sanitizeImported({ prefs: { new_per_review: null } });
        expect(out.prefs.new_per_review).toBe(4);
      });
    });

    it('returns full default prefs object when prefs key is absent', () => {
      const out = sanitizeImported({});
      expect(out.prefs).toEqual({
        show_gloss_by_default: false,
        audio_on_review_reveal: true,
        // audio_listen_first retired → audio_echo_on_grade (2026-04-29).
        // listening_per_review removed: listening is now a separate tab,
        // not an interleave rate.
        audio_echo_on_grade: 'mature_only',
        theme: 'auto',
        target_retention: DEFAULT_TARGET_RETENTION,
        // daily_max_new removed 2026-04-29; default review cap is null (no cap).
        daily_max_reviews: null,
        new_per_review: 4,
      });
    });
  });

  describe('top-level scalar fields', () => {
    it('accepts a numeric current_story', () => {
      expect(sanitizeImported({ current_story: 5 }).current_story).toBe(5);
    });

    it('rejects a non-numeric current_story', () => {
      expect(sanitizeImported({ current_story: 'five' }).current_story).toBe(1);
    });

    it('accepts a string last_opened', () => {
      const ts = '2025-12-31T23:59:59.000Z';
      expect(sanitizeImported({ last_opened: ts }).last_opened).toBe(ts);
    });

    it('rejects a non-string last_opened (uses default ISO now)', () => {
      const out = sanitizeImported({ last_opened: 12345 });
      expect(typeof out.last_opened).toBe('string');
      expect(() => new Date(out.last_opened).toISOString()).not.toThrow();
    });
  });

  describe('unknown / extra keys', () => {
    it('drops keys not in ALLOWED_KEYS', () => {
      const out = sanitizeImported({
        version: CURRENT_VERSION,
        evil_eval: 'rm -rf',
        another: { x: 1 },
      } as Record<string, unknown>);
      expect((out as unknown as Record<string, unknown>).evil_eval).toBeUndefined();
      expect((out as unknown as Record<string, unknown>).another).toBeUndefined();
    });
  });

  describe('null/undefined value handling for top-level keys', () => {
    it('skips ALLOWED keys whose value is null', () => {
      const out = sanitizeImported({ current_story: null });
      expect(out.current_story).toBe(1);
    });

    it('skips ALLOWED keys whose value is undefined', () => {
      const out = sanitizeImported({ current_story: undefined });
      expect(out.current_story).toBe(1);
    });
  });

  describe('round-trip', () => {
    it('a sanitized state passed back through sanitizeImported is stable', () => {
      const seed = sanitizeImported({
        version: CURRENT_VERSION,
        current_story: 7,
        story_progress: { '1': { completed: true }, '7': { completed: true } },
        prefs: { theme: 'dark', target_retention: 0.92 },
        srs: { W00001: makeCard() },
        history: [makeHistoryEntry()],
        daily: { date: todayLocal(), reviewed: 4 },
      });
      const second = sanitizeImported(seed);
      expect(second.current_story).toBe(seed.current_story);
      expect(second.prefs.theme).toBe(seed.prefs.theme);
      expect(second.prefs.target_retention).toBe(seed.prefs.target_retention);
      expect(Object.keys(second.srs)).toEqual(Object.keys(seed.srs));
      expect(second.history.length).toBe(seed.history.length);
      expect(second.story_progress).toEqual(seed.story_progress);
      expect(second.daily.reviewed).toBe(seed.daily.reviewed);
    });
  });
});
