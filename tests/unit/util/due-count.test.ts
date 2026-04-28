/**
 * Tests for the SRS due-count helper. Covers the bug that motivated
 * the helper (2026-04-29): the menu's "Review N" badge was reading
 * an old N because its derivation never re-evaluated the clock. The
 * helper is now strictly time-parameterized so callers can't make
 * the same mistake.
 */
import { describe, it, expect } from 'vitest';
import {
  isCardDue,
  countDueCards,
  nextDueChangeTimestamp,
} from '../../../src/lib/util/due-count';
import type { Card } from '../../../src/lib/state/types';

const NOW = new Date('2026-04-29T00:00:00.000Z');

const card = (id: string, due: string | undefined, status: Card['status'] = 'learning'): Card => ({
  word_id: id,
  first_learned_story: 1,
  context_story: 1,
  context_sentence_idx: 0,
  due: due as unknown as string,
  stability: 1.5,
  difficulty: 5.0,
  elapsed_days: 0,
  scheduled_days: 1,
  learning_steps: 0,
  reps: 1,
  lapses: 0,
  state: 1 as Card['state'],
  status,
});

/* ── isCardDue ───────────────────────────────────────────────────── */

describe('isCardDue', () => {
  it('returns false for null', () => {
    expect(isCardDue(null, NOW)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isCardDue(undefined, NOW)).toBe(false);
  });

  it('returns true when due is missing/empty (treats as overdue)', () => {
    expect(isCardDue(card('W1', undefined), NOW)).toBe(true);
    expect(isCardDue(card('W1', ''), NOW)).toBe(true);
  });

  it('returns true when due is malformed (treats as overdue)', () => {
    expect(isCardDue(card('W1', 'totally-not-a-date'), NOW)).toBe(true);
  });

  it('returns true when due is exactly now (boundary)', () => {
    expect(isCardDue(card('W1', NOW.toISOString()), NOW)).toBe(true);
  });

  it('returns true when due is in the past', () => {
    const past = new Date(NOW.getTime() - 1000).toISOString();
    expect(isCardDue(card('W1', past), NOW)).toBe(true);
  });

  it('returns false when due is in the future', () => {
    const future = new Date(NOW.getTime() + 1000).toISOString();
    expect(isCardDue(card('W1', future), NOW)).toBe(false);
  });

  it('accepts now as a number (epoch ms)', () => {
    const past = new Date(NOW.getTime() - 1000).toISOString();
    expect(isCardDue(card('W1', past), NOW.getTime())).toBe(true);
  });
});

/* ── countDueCards ───────────────────────────────────────────────── */

describe('countDueCards', () => {
  it('returns 0 for null/undefined srs', () => {
    expect(countDueCards(null, NOW)).toBe(0);
    expect(countDueCards(undefined, NOW)).toBe(0);
  });

  it('returns 0 for empty srs', () => {
    expect(countDueCards({}, NOW)).toBe(0);
  });

  it('counts only cards that are due now', () => {
    const past = new Date(NOW.getTime() - 1000).toISOString();
    const future = new Date(NOW.getTime() + 1000).toISOString();
    const srs = {
      W1: card('W1', past),
      W2: card('W2', future),
      W3: card('W3', past),
    };
    expect(countDueCards(srs, NOW)).toBe(2);
  });

  describe('REGRESSION: same srs, different now → different counts', () => {
    it('cards become due as time advances past their due timestamp', () => {
      const inOneHour = new Date(NOW.getTime() + 3600 * 1000).toISOString();
      const srs = { W1: card('W1', inOneHour) };
      // At NOW, the card is not yet due.
      expect(countDueCards(srs, NOW)).toBe(0);
      // 30 minutes later, still not due.
      expect(countDueCards(srs, new Date(NOW.getTime() + 1800 * 1000))).toBe(0);
      // 60 minutes later, now due.
      expect(countDueCards(srs, new Date(NOW.getTime() + 3600 * 1000))).toBe(1);
      // 90 minutes later, still due (overdue).
      expect(countDueCards(srs, new Date(NOW.getTime() + 5400 * 1000))).toBe(1);
    });

    it('a 10-card mix advances from 3 → 7 → 10 due as the clock ticks', () => {
      const srs: Record<string, Card> = {};
      for (let i = 0; i < 10; i += 1) {
        srs[`W${i}`] = card(`W${i}`, new Date(NOW.getTime() + i * 60 * 1000).toISOString());
      }
      // At t=NOW+0, indices 0 (and any with due=NOW) are due.
      expect(countDueCards(srs, NOW)).toBe(1);
      // At t=NOW+5min, indices 0..5 are due (6 cards).
      expect(countDueCards(srs, new Date(NOW.getTime() + 5 * 60 * 1000))).toBe(6);
      // At t=NOW+9min, all 10 are due.
      expect(countDueCards(srs, new Date(NOW.getTime() + 9 * 60 * 1000))).toBe(10);
      // At t=NOW+1d, all 10 still due (overdue).
      expect(countDueCards(srs, new Date(NOW.getTime() + 86400 * 1000))).toBe(10);
    });
  });
});

/* ── nextDueChangeTimestamp ──────────────────────────────────────── */

describe('nextDueChangeTimestamp', () => {
  it('returns null for null/undefined srs', () => {
    expect(nextDueChangeTimestamp(null, NOW)).toBeNull();
    expect(nextDueChangeTimestamp(undefined, NOW)).toBeNull();
  });

  it('returns null for empty srs', () => {
    expect(nextDueChangeTimestamp({}, NOW)).toBeNull();
  });

  it('returns null when every card is already due', () => {
    const past = new Date(NOW.getTime() - 1000).toISOString();
    expect(nextDueChangeTimestamp({ W1: card('W1', past) }, NOW)).toBeNull();
  });

  it('returns null when the only card has no due field (already due)', () => {
    expect(nextDueChangeTimestamp({ W1: card('W1', undefined) }, NOW)).toBeNull();
  });

  it('returns null when due is malformed (already due)', () => {
    expect(nextDueChangeTimestamp({ W1: card('W1', 'garbage') }, NOW)).toBeNull();
  });

  it('returns the only future due timestamp', () => {
    const future = new Date(NOW.getTime() + 60 * 1000);
    const out = nextDueChangeTimestamp({ W1: card('W1', future.toISOString()) }, NOW);
    expect(out).toBe(future.getTime());
  });

  it('returns the EARLIEST future due across multiple cards', () => {
    const t10 = new Date(NOW.getTime() + 10 * 60 * 1000);
    const t30 = new Date(NOW.getTime() + 30 * 60 * 1000);
    const t05 = new Date(NOW.getTime() + 5 * 60 * 1000);
    const srs = {
      W1: card('W1', t10.toISOString()),
      W2: card('W2', t30.toISOString()),
      W3: card('W3', t05.toISOString()),
    };
    expect(nextDueChangeTimestamp(srs, NOW)).toBe(t05.getTime());
  });

  it('skips already-due cards when picking the earliest future change', () => {
    const past = new Date(NOW.getTime() - 1000).toISOString();
    const future = new Date(NOW.getTime() + 60 * 1000);
    const srs = {
      W1: card('W1', past),
      W2: card('W2', future.toISOString()),
    };
    expect(nextDueChangeTimestamp(srs, NOW)).toBe(future.getTime());
  });

  it('strictly future — a card due exactly NOW is treated as already-due', () => {
    expect(nextDueChangeTimestamp({ W1: card('W1', NOW.toISOString()) }, NOW)).toBeNull();
  });

  it('accepts now as a number (epoch ms)', () => {
    const future = new Date(NOW.getTime() + 60 * 1000);
    const out = nextDueChangeTimestamp(
      { W1: card('W1', future.toISOString()) },
      NOW.getTime(),
    );
    expect(out).toBe(future.getTime());
  });

  describe('REGRESSION: drives precise timer scheduling', () => {
    it('the gap (next - now) is the exact ms a setTimeout should wait', () => {
      const future = new Date(NOW.getTime() + 1234);
      const out = nextDueChangeTimestamp(
        { W1: card('W1', future.toISOString()) },
        NOW,
      );
      expect((out ?? 0) - NOW.getTime()).toBe(1234);
    });

    it('after each scheduled wake, the next call returns the NEXT card forward', () => {
      const t1 = new Date(NOW.getTime() + 100);
      const t2 = new Date(NOW.getTime() + 200);
      const t3 = new Date(NOW.getTime() + 300);
      const srs = {
        W1: card('W1', t1.toISOString()),
        W2: card('W2', t2.toISOString()),
        W3: card('W3', t3.toISOString()),
      };
      // First wake target: t1.
      expect(nextDueChangeTimestamp(srs, NOW)).toBe(t1.getTime());
      // After waking at t1, next target is t2.
      expect(nextDueChangeTimestamp(srs, t1)).toBe(t2.getTime());
      // After waking at t2, next target is t3.
      expect(nextDueChangeTimestamp(srs, t2)).toBe(t3.getTime());
      // After waking at t3, nothing left.
      expect(nextDueChangeTimestamp(srs, t3)).toBeNull();
    });
  });
});
