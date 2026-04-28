/**
 * Tests for the review screen's pure keyboard resolver.
 *
 * The 2026-04-29 change: post-reveal, Space (and Enter) now grade Good.
 * Pre-2026-04-29, Space did nothing after the answer was revealed —
 * learners had to reach for the number row, which broke flow on every
 * card. Tests pin the new mapping AND the unchanged pre-reveal
 * Space/Enter → reveal behaviour so neither half regresses
 * independently.
 */
import { describe, it, expect } from 'vitest';
import { resolveReviewKey } from '../../../src/lib/util/review-keymap';

describe('resolveReviewKey — pre-reveal', () => {
  it('Space reveals the answer and preventDefault', () => {
    const r = resolveReviewKey(' ', false);
    expect(r).toEqual({ kind: 'reveal', preventDefault: true });
  });

  it('Enter reveals the answer and preventDefault', () => {
    const r = resolveReviewKey('Enter', false);
    expect(r).toEqual({ kind: 'reveal', preventDefault: true });
  });

  it('number keys are ignored before reveal (no premature grading)', () => {
    expect(resolveReviewKey('1', false)).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('2', false)).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('3', false)).toEqual({ kind: 'ignore' });
  });

  it('u is ignored before reveal (undo only meaningful after grade)', () => {
    expect(resolveReviewKey('u', false)).toEqual({ kind: 'ignore' });
  });

  it('arbitrary keys are ignored', () => {
    expect(resolveReviewKey('a', false)).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('Tab', false)).toEqual({ kind: 'ignore' });
  });
});

describe('resolveReviewKey — post-reveal', () => {
  describe('REGRESSION: Space grades Good', () => {
    it('Space grades Good and preventDefault (default page-down hijack)', () => {
      const r = resolveReviewKey(' ', true);
      expect(r).toEqual({ kind: 'grade', grade: 'good', preventDefault: true });
    });

    it('Enter grades Good and preventDefault', () => {
      const r = resolveReviewKey('Enter', true);
      expect(r).toEqual({ kind: 'grade', grade: 'good', preventDefault: true });
    });
  });

  it('1 grades Again (no preventDefault — number rows are not browser-hijacked)', () => {
    expect(resolveReviewKey('1', true)).toEqual({
      kind: 'grade',
      grade: 'again',
      preventDefault: false,
    });
  });

  it('2 grades Good', () => {
    expect(resolveReviewKey('2', true)).toEqual({
      kind: 'grade',
      grade: 'good',
      preventDefault: false,
    });
  });

  it('3 grades Easy', () => {
    expect(resolveReviewKey('3', true)).toEqual({
      kind: 'grade',
      grade: 'easy',
      preventDefault: false,
    });
  });

  it('u undoes', () => {
    expect(resolveReviewKey('u', true)).toEqual({ kind: 'undo' });
  });

  it('U (capital) also undoes', () => {
    expect(resolveReviewKey('U', true)).toEqual({ kind: 'undo' });
  });

  it('arbitrary keys ignored', () => {
    expect(resolveReviewKey('q', true)).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('Escape', true)).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('4', true)).toEqual({ kind: 'ignore' });
  });
});

describe('resolveReviewKey — focused INPUT elements', () => {
  it('returns ignore when focus is on an INPUT (lowercase tag)', () => {
    expect(resolveReviewKey(' ', false, 'input')).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey(' ', true, 'input')).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey('2', true, 'input')).toEqual({ kind: 'ignore' });
  });

  it('returns ignore when focus is on an INPUT (uppercase tag)', () => {
    expect(resolveReviewKey(' ', true, 'INPUT')).toEqual({ kind: 'ignore' });
  });

  it('returns ignore on TEXTAREA / SELECT (defensive — future-proof)', () => {
    expect(resolveReviewKey(' ', true, 'TEXTAREA')).toEqual({ kind: 'ignore' });
    expect(resolveReviewKey(' ', true, 'SELECT')).toEqual({ kind: 'ignore' });
  });

  it('non-form-element focused tags do NOT suppress shortcuts', () => {
    expect(resolveReviewKey(' ', true, 'BUTTON')).toEqual({
      kind: 'grade',
      grade: 'good',
      preventDefault: true,
    });
    expect(resolveReviewKey(' ', true, 'DIV')).toEqual({
      kind: 'grade',
      grade: 'good',
      preventDefault: true,
    });
  });
});
