import { describe, it, expect, vi } from 'vitest';
import { LRU } from '../../../src/lib/util/lru';

describe('LRU', () => {
  describe('construction', () => {
    it('starts empty', () => {
      const c = new LRU<string, number>(3);
      expect(c.size).toBe(0);
    });

    it('reports size as the underlying map grows', () => {
      const c = new LRU<string, number>(5);
      c.set('a', 1);
      c.set('b', 2);
      expect(c.size).toBe(2);
    });
  });

  describe('get / has', () => {
    it('returns undefined for a missing key', () => {
      const c = new LRU<string, number>(3);
      expect(c.get('nope')).toBeUndefined();
      expect(c.has('nope')).toBe(false);
    });

    it('returns the stored value', () => {
      const c = new LRU<string, number>(3);
      c.set('a', 7);
      expect(c.get('a')).toBe(7);
      expect(c.has('a')).toBe(true);
    });

    it('refreshes recency on get so the entry is no longer the LRU victim', () => {
      const c = new LRU<string, number>(2);
      c.set('a', 1);
      c.set('b', 2);
      // Touch 'a' so 'b' becomes oldest.
      c.get('a');
      c.set('c', 3); // should evict 'b', not 'a'
      expect(c.has('a')).toBe(true);
      expect(c.has('b')).toBe(false);
      expect(c.has('c')).toBe(true);
    });

    it('does NOT call onEvict when get refreshes recency', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(3, onEvict);
      c.set('a', 1);
      c.get('a');
      c.get('a');
      expect(onEvict).not.toHaveBeenCalled();
    });
  });

  describe('set', () => {
    it('overwrites an existing value and refreshes recency', () => {
      const c = new LRU<string, number>(2);
      c.set('a', 1);
      c.set('b', 2);
      c.set('a', 99); // overwrite + refresh
      c.set('c', 3); // should evict 'b' (now oldest)
      expect(c.get('a')).toBe(99);
      expect(c.has('b')).toBe(false);
      expect(c.has('c')).toBe(true);
    });

    it('evicts in insertion order when capacity exceeded', () => {
      const c = new LRU<string, number>(3);
      c.set('a', 1);
      c.set('b', 2);
      c.set('c', 3);
      c.set('d', 4); // evicts 'a'
      expect(c.has('a')).toBe(false);
      expect(c.has('b')).toBe(true);
      expect(c.has('c')).toBe(true);
      expect(c.has('d')).toBe(true);
      expect(c.size).toBe(3);
    });

    it('evicts multiple entries if multiple inserts overflow capacity in sequence', () => {
      const c = new LRU<string, number>(2);
      c.set('a', 1);
      c.set('b', 2);
      c.set('c', 3); // evicts 'a'
      c.set('d', 4); // evicts 'b'
      expect(c.has('a')).toBe(false);
      expect(c.has('b')).toBe(false);
      expect(c.has('c')).toBe(true);
      expect(c.has('d')).toBe(true);
    });

    it('calls onEvict exactly once per evicted entry, with the evicted key+value', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(2, onEvict);
      c.set('a', 1);
      c.set('b', 2);
      c.set('c', 3);
      expect(onEvict).toHaveBeenCalledTimes(1);
      expect(onEvict).toHaveBeenCalledWith('a', 1);
    });

    it('does NOT call onEvict when overwriting an existing key', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(2, onEvict);
      c.set('a', 1);
      c.set('a', 2);
      expect(onEvict).not.toHaveBeenCalled();
    });
  });

  describe('clear', () => {
    it('removes all entries', () => {
      const c = new LRU<string, number>(3);
      c.set('a', 1);
      c.set('b', 2);
      c.clear();
      expect(c.size).toBe(0);
      expect(c.has('a')).toBe(false);
      expect(c.has('b')).toBe(false);
    });

    it('calls onEvict for every entry on clear (when callback provided)', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(3, onEvict);
      c.set('a', 1);
      c.set('b', 2);
      c.clear();
      expect(onEvict).toHaveBeenCalledTimes(2);
      expect(onEvict).toHaveBeenCalledWith('a', 1);
      expect(onEvict).toHaveBeenCalledWith('b', 2);
    });

    it('does not throw when no onEvict is provided', () => {
      const c = new LRU<string, number>(3);
      c.set('a', 1);
      expect(() => c.clear()).not.toThrow();
    });

    it('clearing an empty cache is a no-op', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(3, onEvict);
      c.clear();
      expect(onEvict).not.toHaveBeenCalled();
    });
  });

  describe('capacity edge cases', () => {
    it('capacity of 1 keeps only the most recently inserted entry', () => {
      const c = new LRU<string, number>(1);
      c.set('a', 1);
      c.set('b', 2);
      expect(c.has('a')).toBe(false);
      expect(c.get('b')).toBe(2);
      expect(c.size).toBe(1);
    });

    it('capacity of 0 evicts every insert immediately', () => {
      const onEvict = vi.fn();
      const c = new LRU<string, number>(0, onEvict);
      c.set('a', 1);
      expect(c.size).toBe(0);
      expect(c.has('a')).toBe(false);
      expect(onEvict).toHaveBeenCalledWith('a', 1);
    });

    it('large capacity holds many entries without eviction', () => {
      const c = new LRU<number, number>(1000);
      for (let i = 0; i < 500; i++) c.set(i, i * 2);
      expect(c.size).toBe(500);
      expect(c.get(0)).toBe(0);
      expect(c.get(499)).toBe(998);
    });
  });

  describe('non-string keys', () => {
    it('works with number keys', () => {
      const c = new LRU<number, string>(2);
      c.set(1, 'one');
      c.set(2, 'two');
      expect(c.get(1)).toBe('one');
      expect(c.get(2)).toBe('two');
    });

    it('works with object keys (identity-based)', () => {
      const k1 = { id: 1 };
      const k2 = { id: 1 }; // different identity
      const c = new LRU<object, string>(2);
      c.set(k1, 'first');
      c.set(k2, 'second');
      expect(c.get(k1)).toBe('first');
      expect(c.get(k2)).toBe('second');
      expect(c.size).toBe(2);
    });
  });

  describe('value semantics', () => {
    it('stores undefined values that round-trip via has/get', () => {
      const c = new LRU<string, undefined>(2);
      c.set('a', undefined);
      // has() reports presence; get() returns the value (which is undefined).
      expect(c.has('a')).toBe(true);
      expect(c.get('a')).toBeUndefined();
    });

    it('stores null distinct from missing', () => {
      const c = new LRU<string, null | number>(2);
      c.set('a', null);
      expect(c.has('a')).toBe(true);
      expect(c.get('a')).toBeNull();
    });
  });
});
