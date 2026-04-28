import { describe, it, expect } from 'vitest';
import { escapeHtml } from '../../../src/lib/util/html';

describe('escapeHtml', () => {
  describe('null-safety', () => {
    it('returns empty string for null', () => {
      expect(escapeHtml(null)).toBe('');
    });

    it('returns empty string for undefined', () => {
      expect(escapeHtml(undefined)).toBe('');
    });

    it('does NOT collapse the string "null" — only the actual null value', () => {
      expect(escapeHtml('null')).toBe('null');
    });
  });

  describe('numeric input', () => {
    it('coerces numbers to string', () => {
      expect(escapeHtml(42)).toBe('42');
    });

    it('handles zero (a falsy non-null number)', () => {
      expect(escapeHtml(0)).toBe('0');
    });

    it('handles negative numbers and floats', () => {
      expect(escapeHtml(-3.14)).toBe('-3.14');
    });
  });

  describe('escaping', () => {
    it('escapes ampersand', () => {
      expect(escapeHtml('a & b')).toBe('a &amp; b');
    });

    it('escapes less-than', () => {
      expect(escapeHtml('1 < 2')).toBe('1 &lt; 2');
    });

    it('escapes greater-than', () => {
      expect(escapeHtml('a > b')).toBe('a &gt; b');
    });

    it('escapes double quote', () => {
      expect(escapeHtml('say "hi"')).toBe('say &quot;hi&quot;');
    });

    it('escapes single quote / apostrophe', () => {
      expect(escapeHtml("it's")).toBe('it&#39;s');
    });

    it('escapes a full <script> injection', () => {
      const out = escapeHtml('<script>alert("x")</script>');
      expect(out).toBe('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
    });

    it('escapes mixed special chars in one pass', () => {
      const out = escapeHtml(`<a href="x">&'</a>`);
      expect(out).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;');
    });

    it('does NOT double-escape entities (because input is treated as raw text)', () => {
      // Note: this is intentional — escapeHtml is for raw user/source text,
      // not for re-encoding already-escaped strings.
      expect(escapeHtml('&amp;')).toBe('&amp;amp;');
    });
  });

  describe('idempotency on safe input', () => {
    it('returns ASCII letters unchanged', () => {
      expect(escapeHtml('hello world')).toBe('hello world');
    });

    it('returns empty string unchanged', () => {
      expect(escapeHtml('')).toBe('');
    });

    it('returns Japanese text unchanged', () => {
      expect(escapeHtml('猫が歩きます。')).toBe('猫が歩きます。');
    });

    it('returns whitespace and newlines as-is', () => {
      expect(escapeHtml(' \n\t\r ')).toBe(' \n\t\r ');
    });
  });
});
