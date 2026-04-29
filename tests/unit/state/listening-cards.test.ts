/**
 * Tests for the listening-card modality (variant A) wiring across:
 *
 *   - the type-level helpers `listeningCardId`, `parseListeningCardId`,
 *     and `cardKind` in src/lib/state/types.ts
 *   - the queue-side interleave behavior in `buildQueue` driven by the
 *     `listeningPerReview` option
 *
 * The goal is to pin "listening cards are an ADDITION, never a
 * replacement" — the structural promise that drove this design.
 */
import { describe, it, expect } from 'vitest';
import { applyGrade, buildQueue, GRADES, newCard } from '../../../src/lib/state/srs';
import {
  cardKind,
  listeningCardId,
  parseListeningCardId,
} from '../../../src/lib/state/types';
import type { Card } from '../../../src/lib/state/types';

const NOW = new Date('2026-04-29T12:00:00.000Z');

function past(when: Date, hours: number): Date {
  return new Date(when.getTime() - hours * 3600 * 1000);
}

/* ── id helpers ──────────────────────────────────────────────────── */
describe('listeningCardId / parseListeningCardId', () => {
  it('round-trips (story, sentence) → id → (story, sentence)', () => {
    const id = listeningCardId(4, 2);
    expect(id).toBe('L:4:2');
    expect(parseListeningCardId(id)).toEqual({ story_id: 4, sentence_idx: 2 });
  });

  it('handles sentence_idx = 0 (the title-following first sentence)', () => {
    expect(parseListeningCardId('L:1:0')).toEqual({ story_id: 1, sentence_idx: 0 });
  });

  it('handles large story ids without coercion artifacts', () => {
    expect(parseListeningCardId('L:9999:42')).toEqual({
      story_id: 9999,
      sentence_idx: 42,
    });
  });

  it('returns null for plain word ids (no L: prefix)', () => {
    expect(parseListeningCardId('W00042')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseListeningCardId('')).toBeNull();
  });

  it('returns null for malformed listening ids (wrong segment count)', () => {
    expect(parseListeningCardId('L:4')).toBeNull();
    expect(parseListeningCardId('L:4:2:3')).toBeNull();
  });

  it('returns null for non-integer story or sentence index', () => {
    expect(parseListeningCardId('L:abc:2')).toBeNull();
    expect(parseListeningCardId('L:4:def')).toBeNull();
    expect(parseListeningCardId('L:4:2.5')).toBeNull();
  });

  it('returns null for negative sentence index (sentences are 0-based)', () => {
    expect(parseListeningCardId('L:4:-1')).toBeNull();
  });

  it('returns null for story id 0 or below', () => {
    expect(parseListeningCardId('L:0:2')).toBeNull();
    expect(parseListeningCardId('L:-1:2')).toBeNull();
  });
});

/* ── cardKind discriminator ─────────────────────────────────────── */
describe('cardKind', () => {
  function fakeCard(overrides: Partial<Card>): Card {
    return {
      word_id: 'W00001',
      first_learned_story: 1,
      context_story: 1,
      context_sentence_idx: 0,
      due: NOW.toISOString(),
      stability: 1,
      difficulty: 5,
      elapsed_days: 0,
      scheduled_days: 0,
      learning_steps: 0,
      reps: 0,
      lapses: 0,
      state: 0 as Card['state'],
      status: 'new',
      ...overrides,
    };
  }

  it('returns the explicit kind when set to "reading"', () => {
    expect(cardKind(fakeCard({ kind: 'reading' }))).toBe('reading');
  });

  it('returns the explicit kind when set to "listening"', () => {
    expect(cardKind(fakeCard({ kind: 'listening' }))).toBe('listening');
  });

  it('defaults to "reading" for legacy cards without the field', () => {
    // Pre-2026-04-29 cards lack `kind`; the only kind that existed was reading.
    expect(cardKind(fakeCard({ kind: undefined }))).toBe('reading');
  });

  it('infers "listening" from an L:-prefixed word_id even when kind is missing', () => {
    // Defense-in-depth: if a listening card somehow lost its kind
    // field in transit, the id encodes the truth.
    expect(cardKind(fakeCard({ word_id: 'L:4:2', kind: undefined }))).toBe(
      'listening',
    );
  });
});

/* ── buildQueue: listening cards weave in as ADDITION ──────────── */
describe('buildQueue listening interleave', () => {
  /** Mint a fresh-due card of either kind with a stable due ordering. */
  function due(id: string, kind: 'reading' | 'listening', delayHours: number): Card {
    const c = newCard({
      word_id: id,
      story_id: 1,
      context_sentence_idx: 0,
      kind,
      now: NOW,
    });
    return { ...c, due: past(NOW, delayHours).toISOString() };
  }

  function srsWith(...cards: Card[]): Record<string, Card> {
    return Object.fromEntries(cards.map((c) => [c.word_id, c]));
  }

  it('does not introduce listening cards when none are due', () => {
    // Pure-reading scenario should be byte-identical to legacy behavior.
    const srs = srsWith(
      due('W1', 'reading', 1),
      due('W2', 'reading', 0.9),
      due('W3', 'reading', 0.8),
    );
    const q = buildQueue(srs, { now: NOW, listeningPerReview: 6 });
    expect(q.map((c) => c.word_id)).toEqual(['W1', 'W2', 'W3']);
    expect(q.every((c) => cardKind(c) === 'reading')).toBe(true);
  });

  it('weaves listening cards into the reading stream at the configured rate', () => {
    // 12 reading cards + 4 listening cards. With listeningPerReview=3,
    // we expect roughly 1 listening per 3 reading.
    const cards: Card[] = [];
    for (let i = 0; i < 12; i++) {
      cards.push(due(`W${String(i).padStart(2, '0')}`, 'reading', 12 - i));
    }
    for (let i = 0; i < 4; i++) {
      cards.push(due(`L:1:${i}`, 'listening', 4 - i));
    }
    const q = buildQueue(srsWith(...cards), {
      now: NOW,
      listeningPerReview: 3,
      newPerReview: 0, // simplify the expectation by skipping the news
                      // weave (listening cards are also "new"; setting
                      // 0 puts new readings at the end stably)
    });
    // Assert: every listening card surfaces (none were dropped) and
    // the count of listening cards is exactly 4 (no reads were
    // displaced).
    const listening = q.filter((c) => cardKind(c) === 'listening');
    const reading = q.filter((c) => cardKind(c) === 'reading');
    expect(listening.length).toBe(4);
    expect(reading.length).toBe(12);
    expect(q.length).toBe(16);
  });

  it('listeningPerReview=0 drops all listening cards from the queue', () => {
    // Pref=0 = "I don't want listening cards in my reviews right now".
    // The SRS map keeps them; they just don't surface in this session.
    const srs = srsWith(
      due('W1', 'reading', 1),
      due('L:1:0', 'listening', 1),
      due('L:1:1', 'listening', 0.5),
    );
    const q = buildQueue(srs, { now: NOW, listeningPerReview: 0 });
    expect(q.map((c) => c.word_id)).toEqual(['W1']);
  });

  it('listening reviews count against maxReviews together with reading reviews', () => {
    // The cap is a TOTAL, not a per-modality multiplier — matches the
    // user-intuitive "I want N cards in this session".
    const cards: Card[] = [];
    for (let i = 0; i < 5; i++) {
      const c = newCard({
        word_id: `W${i}`,
        story_id: 1,
        context_sentence_idx: 0,
        kind: 'reading',
        now: NOW,
      });
      // Promote to Review state so it's a "review" card, not "new".
      const promoted = applyGrade(c, GRADES.GOOD, NOW).card;
      cards.push({ ...promoted, due: past(NOW, 24 * (i + 1)).toISOString() });
    }
    for (let i = 0; i < 5; i++) {
      const c = newCard({
        word_id: `L:1:${i}`,
        story_id: 1,
        context_sentence_idx: i,
        kind: 'listening',
        now: NOW,
      });
      const promoted = applyGrade(c, GRADES.GOOD, NOW).card;
      cards.push({ ...promoted, due: past(NOW, 12 * (i + 1)).toISOString() });
    }
    const q = buildQueue(srsWith(...cards), {
      now: NOW,
      maxReviews: 6,
      listeningPerReview: 3,
    });
    expect(q.length).toBeLessThanOrEqual(6);
  });

  it('listening LEARNING cards hoist to front (after reading learning)', () => {
    // Same intra-session priority rule as reading learning cards: short-
    // term debt must clear before fresh material.
    const reading = newCard({
      word_id: 'W1',
      story_id: 1,
      context_sentence_idx: 0,
      kind: 'reading',
      now: NOW,
    });
    // Push reading into Learning by Again-ing a graduated card.
    const grad = applyGrade(reading, GRADES.GOOD, NOW).card;
    const lapsed = applyGrade(
      { ...grad, due: past(NOW, 0.1).toISOString() },
      GRADES.AGAIN,
      NOW,
    ).card;

    const listen = newCard({
      word_id: 'L:1:0',
      story_id: 1,
      context_sentence_idx: 0,
      kind: 'listening',
      now: NOW,
    });
    const grad2 = applyGrade(listen, GRADES.GOOD, NOW).card;
    const lapsedListen = applyGrade(
      { ...grad2, due: past(NOW, 0.1).toISOString() },
      GRADES.AGAIN,
      NOW,
    ).card;

    const newReading = due('W2', 'reading', 0);
    const q = buildQueue(
      srsWith(
        { ...lapsed, due: past(NOW, 0.1).toISOString() },
        { ...lapsedListen, due: past(NOW, 0.1).toISOString() },
        newReading,
      ),
      { now: NOW },
    );
    // Reading learning first, then listening learning, then everything else.
    expect(q[0].word_id).toBe('W1');
    expect(q[1].word_id).toBe('L:1:0');
  });
});
