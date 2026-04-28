/**
 * Tests for the "show only what the learner has seen" filters used
 * by the vocab and grammar tabs (added 2026-04-29).
 */
import { describe, it, expect } from 'vitest';
import {
  isKnownWord,
  filterKnownWords,
  isSeenGrammar,
  filterSeenGrammar,
} from '../../../src/lib/util/known-filters';
import type { Card } from '../../../src/lib/state/types';
import type { VocabIndexRow, GrammarPoint } from '../../../src/lib/data/types';

const card = (word_id: string, status: Card['status'] = 'learning'): Card => ({
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
  status,
});

const row = (id: string, overrides: Partial<VocabIndexRow> = {}): VocabIndexRow => ({
  id,
  shard: '00',
  surface: '猫',
  kana: 'ねこ',
  reading: 'neko',
  short_meaning: 'cat',
  occurrences: 1,
  ...overrides,
});

const gp = (id: string, intro_in_story: number | null | undefined): GrammarPoint => ({
  id,
  title: id,
  intro_in_story,
});

/* ── isKnownWord / filterKnownWords ───────────────────────────────── */

describe('isKnownWord', () => {
  it('returns false for empty srs', () => {
    expect(isKnownWord({ id: 'W001' }, {})).toBe(false);
  });

  it('returns false for null/undefined srs', () => {
    expect(isKnownWord({ id: 'W001' }, null)).toBe(false);
    expect(isKnownWord({ id: 'W001' }, undefined)).toBe(false);
  });

  it('returns true when the word has any srs card', () => {
    expect(isKnownWord({ id: 'W001' }, { W001: card('W001') })).toBe(true);
  });

  it('returns true regardless of card status (new/learning/mature/leech all count)', () => {
    for (const st of ['new', 'learning', 'young', 'mature', 'leech'] as const) {
      expect(isKnownWord({ id: 'W001' }, { W001: card('W001', st) })).toBe(true);
    }
  });

  it('returns false when only OTHER words are in srs', () => {
    expect(isKnownWord({ id: 'W001' }, { W002: card('W002'), W003: card('W003') })).toBe(false);
  });
});

describe('filterKnownWords', () => {
  it('returns empty when srs is empty', () => {
    expect(filterKnownWords([row('W001'), row('W002')], {})).toEqual([]);
  });

  it('returns only rows with srs cards', () => {
    const out = filterKnownWords(
      [row('W001'), row('W002'), row('W003')],
      { W001: card('W001'), W003: card('W003') },
    );
    expect(out.map((r) => r.id)).toEqual(['W001', 'W003']);
  });

  it('preserves input order of the kept rows', () => {
    const out = filterKnownWords(
      [row('W003'), row('W001'), row('W002')],
      { W001: card('W001'), W002: card('W002'), W003: card('W003') },
    );
    expect(out.map((r) => r.id)).toEqual(['W003', 'W001', 'W002']);
  });

  it('handles a 100-row corpus where 17 are known', () => {
    const rows = Array.from({ length: 100 }, (_, i) => row(`W${String(i).padStart(3, '0')}`));
    const known: Record<string, Card> = {};
    for (let i = 0; i < 100; i += 6) known[`W${String(i).padStart(3, '0')}`] = card(`W${String(i).padStart(3, '0')}`);
    const out = filterKnownWords(rows, known);
    expect(out).toHaveLength(17);
  });
});

/* ── isSeenGrammar / filterSeenGrammar ────────────────────────────── */

describe('isSeenGrammar', () => {
  it('returns true for a positive intro_in_story', () => {
    expect(isSeenGrammar(gp('G001', 1))).toBe(true);
    expect(isSeenGrammar(gp('G001', 42))).toBe(true);
  });

  it('returns false for null', () => {
    expect(isSeenGrammar(gp('G001', null))).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isSeenGrammar(gp('G001', undefined))).toBe(false);
  });

  it('returns false for zero', () => {
    expect(isSeenGrammar(gp('G001', 0))).toBe(false);
  });

  it('returns false for negative numbers', () => {
    expect(isSeenGrammar(gp('G001', -1))).toBe(false);
  });

  it('returns false for NaN/Infinity', () => {
    expect(isSeenGrammar(gp('G001', NaN))).toBe(false);
    expect(isSeenGrammar(gp('G001', Infinity))).toBe(false);
  });

  it('returns false for the wrong type cast through', () => {
    expect(isSeenGrammar({ intro_in_story: '1' as unknown as number })).toBe(false);
  });
});

describe('filterSeenGrammar', () => {
  it('returns empty when nothing has been introduced', () => {
    const points = [gp('G001', null), gp('G002', null), gp('G003', undefined)];
    expect(filterSeenGrammar(points)).toEqual([]);
  });

  it('returns only the introduced points', () => {
    const points = [gp('G001', 1), gp('G002', null), gp('G003', 3), gp('G004', undefined)];
    expect(filterSeenGrammar(points).map((p) => p.id)).toEqual(['G001', 'G003']);
  });

  it('preserves input order', () => {
    const points = [gp('G003', 3), gp('G001', 1), gp('G002', 2)];
    expect(filterSeenGrammar(points).map((p) => p.id)).toEqual(['G003', 'G001', 'G002']);
  });

  it('mirrors the real-corpus shape — 49 total, 18 introduced (at write time)', () => {
    // Synthetic: half-introduced sample. The exact count would shift
    // as the corpus grows; the assertion is on the proportion.
    const points = [
      ...Array.from({ length: 18 }, (_, i) => gp(`G${i}`, i + 1)),
      ...Array.from({ length: 31 }, (_, i) => gp(`Gn${i}`, null)),
    ];
    const out = filterSeenGrammar(points);
    expect(out).toHaveLength(18);
    expect(out.every((p) => isSeenGrammar(p))).toBe(true);
  });
});
