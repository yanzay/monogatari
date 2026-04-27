/**
 * Tiny LRU cache. ~30 lines, no deps. Used for in-memory story JSON and
 * <audio> elements so a long session doesn't leak unbounded memory.
 */
export class LRU<K, V> {
  private readonly map = new Map<K, V>();
  constructor(
    private readonly capacity: number,
    private readonly onEvict?: (key: K, value: V) => void,
  ) {}

  get(key: K): V | undefined {
    if (!this.map.has(key)) return undefined;
    const v = this.map.get(key)!;
    // Refresh recency by re-inserting (Map preserves insertion order).
    this.map.delete(key);
    this.map.set(key, v);
    return v;
  }

  has(key: K): boolean {
    return this.map.has(key);
  }

  set(key: K, value: V): void {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, value);
    while (this.map.size > this.capacity) {
      const oldest = this.map.keys().next().value as K;
      const v = this.map.get(oldest)!;
      this.map.delete(oldest);
      this.onEvict?.(oldest, v);
    }
  }

  clear(): void {
    if (this.onEvict) {
      for (const [k, v] of this.map) this.onEvict(k, v);
    }
    this.map.clear();
  }

  get size(): number {
    return this.map.size;
  }
}
