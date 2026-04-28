/**
 * Tests for $lib/data/audio — the singleton audio playback layer with
 * an LRU cache of <audio> elements. We mock the browser Audio class so
 * we can assert on play/pause and observe lifecycle without ever
 * actually loading a media file.
 *
 * `$app/paths` is mocked to a known base. Because the `audio.ts`
 * module captures `base` at import time, tests must ALWAYS use a
 * fresh dynamic import after mocking — `vi.resetModules()` in
 * beforeEach guarantees that.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('$app/paths', () => ({ base: '/monogatari' }));

class FakeAudio {
  src: string;
  preload = '';
  currentTime = 0;
  paused = true;
  onended: (() => void) | null = null;
  loadCalls = 0;
  playCalls = 0;
  pauseCalls = 0;
  removeAttributeCalls: string[] = [];
  removedAttrs = new Set<string>();
  constructor(src: string) {
    this.src = src;
    FakeAudio.instances.push(this);
  }
  play() {
    this.playCalls += 1;
    this.paused = false;
    return Promise.resolve();
  }
  pause() {
    this.pauseCalls += 1;
    this.paused = true;
  }
  load() {
    this.loadCalls += 1;
  }
  removeAttribute(name: string) {
    this.removeAttributeCalls.push(name);
    this.removedAttrs.add(name);
    if (name === 'src') this.src = '';
  }
  static instances: FakeAudio[] = [];
  static reset() {
    FakeAudio.instances = [];
  }
}

beforeEach(() => {
  FakeAudio.reset();
  // Reset the singleton state in audio.ts so each test starts fresh.
  vi.resetModules();
  // Stub global Audio constructor.
  (globalThis as unknown as { Audio: typeof FakeAudio }).Audio = FakeAudio;
});

async function loadModule() {
  return await import('../../../src/lib/data/audio');
}

describe('audioFor', () => {
  it('returns null for null/undefined/empty src', async () => {
    const m = await loadModule();
    expect(m.audioFor(null)).toBeNull();
    expect(m.audioFor(undefined)).toBeNull();
    expect(m.audioFor('')).toBeNull();
  });

  it('prepends base to a relative path', async () => {
    const m = await loadModule();
    const a = m.audioFor('audio/story_1/s0.mp3');
    expect(a).toBeDefined();
    expect((a as unknown as FakeAudio).src).toBe('/monogatari/audio/story_1/s0.mp3');
  });

  it('does NOT prepend base to an absolute path starting with /', async () => {
    const m = await loadModule();
    const a = m.audioFor('/abs/path.mp3');
    expect((a as unknown as FakeAudio).src).toBe('/abs/path.mp3');
  });

  it('does NOT prepend base to an http URL', async () => {
    const m = await loadModule();
    const a = m.audioFor('http://example.com/x.mp3');
    expect((a as unknown as FakeAudio).src).toBe('http://example.com/x.mp3');
  });

  it('does NOT prepend base to an https URL', async () => {
    const m = await loadModule();
    const a = m.audioFor('https://example.com/x.mp3');
    expect((a as unknown as FakeAudio).src).toBe('https://example.com/x.mp3');
  });

  it('sets preload="auto" on newly created audio elements', async () => {
    const m = await loadModule();
    const a = m.audioFor('audio/x.mp3') as unknown as FakeAudio;
    expect(a.preload).toBe('auto');
  });

  it('caches by URL — same src returns the same element', async () => {
    const m = await loadModule();
    const a = m.audioFor('audio/x.mp3');
    const b = m.audioFor('audio/x.mp3');
    expect(a).toBe(b);
    // Only one underlying instance was constructed.
    expect(FakeAudio.instances).toHaveLength(1);
  });

  it('different srcs allocate distinct elements', async () => {
    const m = await loadModule();
    m.audioFor('audio/a.mp3');
    m.audioFor('audio/b.mp3');
    expect(FakeAudio.instances).toHaveLength(2);
  });
});

describe('LRU eviction (cap = 64)', () => {
  it('evicts the oldest element when capacity is exceeded', async () => {
    const m = await loadModule();
    // 65 unique srcs → first one evicted.
    for (let i = 0; i < 65; i++) {
      m.audioFor(`audio/${i}.mp3`);
    }
    expect(FakeAudio.instances).toHaveLength(65);
    // The 0th instance should have been evicted: pause + removeAttribute('src') + load
    const evicted = FakeAudio.instances[0];
    expect(evicted.pauseCalls).toBeGreaterThanOrEqual(1);
    expect(evicted.removedAttrs.has('src')).toBe(true);
    expect(evicted.loadCalls).toBeGreaterThanOrEqual(1);
    // The 64th (most recently added) should be untouched.
    const recent = FakeAudio.instances[64];
    expect(recent.pauseCalls).toBe(0);
  });
});

describe('playOnce', () => {
  it('calls play() on the requested element', async () => {
    const m = await loadModule();
    m.playOnce('audio/x.mp3');
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].playCalls).toBe(1);
  });

  it('rewinds currentTime to 0 before playing', async () => {
    const m = await loadModule();
    const first = m.audioFor('audio/x.mp3') as unknown as FakeAudio;
    first.currentTime = 5;
    m.playOnce('audio/x.mp3');
    expect(first.currentTime).toBe(0);
  });

  it('pauses the previously-playing element when starting a new one', async () => {
    const m = await loadModule();
    m.playOnce('audio/a.mp3');
    const a = FakeAudio.instances[0];
    m.playOnce('audio/b.mp3');
    expect(a.pauseCalls).toBeGreaterThanOrEqual(1);
  });

  it('invokes the onEnd callback when the audio ends', async () => {
    const m = await loadModule();
    const onEnd = vi.fn();
    m.playOnce('audio/x.mp3', { onEnd });
    const inst = FakeAudio.instances[0];
    // Simulate the browser firing 'ended'.
    inst.onended?.();
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('is a no-op when src is null/undefined/empty', async () => {
    const m = await loadModule();
    m.playOnce(null);
    m.playOnce(undefined);
    m.playOnce('');
    expect(FakeAudio.instances).toHaveLength(0);
  });

  it('subsequent playOnce of same src reuses cached element', async () => {
    const m = await loadModule();
    m.playOnce('audio/x.mp3');
    m.playOnce('audio/x.mp3');
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].playCalls).toBe(2);
  });
});

describe('stopCurrent', () => {
  it('pauses the currently playing element and rewinds it', async () => {
    const m = await loadModule();
    m.playOnce('audio/x.mp3');
    const inst = FakeAudio.instances[0];
    inst.currentTime = 3.2;
    m.stopCurrent();
    expect(inst.pauseCalls).toBeGreaterThanOrEqual(1);
    expect(inst.currentTime).toBe(0);
  });

  it('does not throw when nothing is playing', async () => {
    const m = await loadModule();
    expect(() => m.stopCurrent()).not.toThrow();
  });

  it('clears the sequence-playing flag', async () => {
    const m = await loadModule();
    m.setSequencePlaying(true);
    m.stopCurrent();
    expect(m.isSequencePlaying()).toBe(false);
  });

  it('subsequent playOnce after stop does not double-pause the previous element', async () => {
    const m = await loadModule();
    m.playOnce('audio/x.mp3');
    const a = FakeAudio.instances[0];
    m.stopCurrent();
    const pauseCount = a.pauseCalls;
    m.playOnce('audio/y.mp3');
    // Old element should NOT be paused again — current was already cleared.
    expect(a.pauseCalls).toBe(pauseCount);
  });
});

describe('sequence flag accessors', () => {
  it('isSequencePlaying defaults to false', async () => {
    const m = await loadModule();
    expect(m.isSequencePlaying()).toBe(false);
  });

  it('setSequencePlaying flips the flag', async () => {
    const m = await loadModule();
    m.setSequencePlaying(true);
    expect(m.isSequencePlaying()).toBe(true);
    m.setSequencePlaying(false);
    expect(m.isSequencePlaying()).toBe(false);
  });
});
