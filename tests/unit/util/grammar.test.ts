import { describe, it, expect } from 'vitest';
import { isGrammarEntryIncomplete } from '../../../src/lib/util/grammar';
import type { GrammarPoint } from '../../../src/lib/data/types';

function gp(overrides: Partial<GrammarPoint> = {}): GrammarPoint {
  return {
    id: 'G001_test',
    title: 'Test Grammar',
    short: 'A short description',
    long: 'A longer multi-paragraph explanation.',
    ...overrides,
  };
}

describe('isGrammarEntryIncomplete', () => {
  it('returns true for null', () => {
    expect(isGrammarEntryIncomplete(null)).toBe(true);
  });

  it('returns true for undefined', () => {
    expect(isGrammarEntryIncomplete(undefined)).toBe(true);
  });

  it('returns false for a fully-populated entry', () => {
    expect(isGrammarEntryIncomplete(gp())).toBe(false);
  });

  it('returns true when _needs_review is set', () => {
    expect(isGrammarEntryIncomplete(gp({ _needs_review: true }))).toBe(true);
  });

  it('returns false when _needs_review is explicitly false', () => {
    expect(isGrammarEntryIncomplete(gp({ _needs_review: false }))).toBe(false);
  });

  describe('title validation', () => {
    it('returns true when title is missing', () => {
      expect(isGrammarEntryIncomplete(gp({ title: undefined }))).toBe(true);
    });

    it('returns true when title is empty string', () => {
      expect(isGrammarEntryIncomplete(gp({ title: '' }))).toBe(true);
    });

    it('returns true when title equals the id (auto-scaffolded placeholder)', () => {
      expect(isGrammarEntryIncomplete(gp({ id: 'G001_xxx', title: 'G001_xxx' }))).toBe(true);
    });

    it('returns true when title is whitespace-only matching the id', () => {
      expect(isGrammarEntryIncomplete(gp({ id: 'G001_xxx', title: '  G001_xxx  ' }))).toBe(true);
    });

    it('returns false when title differs from id even if it contains the id', () => {
      expect(
        isGrammarEntryIncomplete(gp({ id: 'G001_wa', title: 'wa: topic marker (G001_wa)' })),
      ).toBe(false);
    });
  });

  describe('short validation', () => {
    it('returns true when short is missing', () => {
      expect(isGrammarEntryIncomplete(gp({ short: undefined }))).toBe(true);
    });

    it('returns true when short is empty string', () => {
      expect(isGrammarEntryIncomplete(gp({ short: '' }))).toBe(true);
    });

    it('returns true when short matches the canonical placeholder string', () => {
      expect(
        isGrammarEntryIncomplete(
          gp({ short: '(added by state updater — fill in description)' }),
        ),
      ).toBe(true);
    });

    it('returns true when short matches the shorter placeholder string', () => {
      expect(isGrammarEntryIncomplete(gp({ short: '(added by state updater)' }))).toBe(true);
    });

    it('returns true when short is literally TODO', () => {
      expect(isGrammarEntryIncomplete(gp({ short: 'TODO' }))).toBe(true);
    });

    it('returns true when short is whitespace-padded TODO', () => {
      expect(isGrammarEntryIncomplete(gp({ short: '  TODO  ' }))).toBe(true);
    });
  });

  describe('long validation', () => {
    it('returns true when long is missing', () => {
      expect(isGrammarEntryIncomplete(gp({ long: undefined }))).toBe(true);
    });

    it('returns true when long is empty', () => {
      expect(isGrammarEntryIncomplete(gp({ long: '' }))).toBe(true);
    });

    it('returns true when long is whitespace-only', () => {
      expect(isGrammarEntryIncomplete(gp({ long: '   \n\t  ' }))).toBe(true);
    });

    it('returns false for a long with leading/trailing whitespace but real content', () => {
      expect(isGrammarEntryIncomplete(gp({ long: '   real content here  ' }))).toBe(false);
    });
  });
});
