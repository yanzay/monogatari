/**
 * Pure keyboard-shortcut resolver for the review screen.
 *
 * Lives outside the Svelte component so it's unit-testable in
 * isolation — keyboard handling is the kind of code that quietly
 * regresses (rebinding a key, swapping which grade Space maps to,
 * forgetting an INPUT-element guard) and a pure function is easy to
 * pin with a clean test matrix.
 *
 * The result is a discriminated union the caller switches on. The
 * caller is responsible for doing the actual work (revealing the
 * answer, calling grade(), undoing, calling preventDefault()).
 *
 * Hard rule: when the focused element is an <input>, the handler
 * returns 'ignore' so typing into a future search/notes field
 * doesn't get hijacked.
 */
export type ReviewAction =
  | { kind: 'ignore' }
  | { kind: 'reveal'; preventDefault: true }
  | { kind: 'grade'; grade: 'again' | 'good' | 'easy'; preventDefault: boolean }
  | { kind: 'undo' };

const IGNORED_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export function resolveReviewKey(
  key: string,
  revealed: boolean,
  focusedTag?: string,
): ReviewAction {
  if (focusedTag && IGNORED_TAGS.has(focusedTag.toUpperCase())) {
    return { kind: 'ignore' };
  }

  // Pre-reveal: Space and Enter both reveal the answer.
  if (!revealed) {
    if (key === ' ' || key === 'Enter') {
      return { kind: 'reveal', preventDefault: true };
    }
    return { kind: 'ignore' };
  }

  // Post-reveal: Space and Enter grade Good (the common case). Number
  // keys remain available for the less-common Again/Easy verdicts so
  // power users still have explicit control.
  if (key === ' ' || key === 'Enter') {
    return { kind: 'grade', grade: 'good', preventDefault: true };
  }
  if (key === '1') return { kind: 'grade', grade: 'again', preventDefault: false };
  if (key === '2') return { kind: 'grade', grade: 'good', preventDefault: false };
  if (key === '3') return { kind: 'grade', grade: 'easy', preventDefault: false };
  if (key === 'u' || key === 'U') return { kind: 'undo' };
  return { kind: 'ignore' };
}
