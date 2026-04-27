import { base } from '$app/paths';
import { LRU } from '$lib/util/lru';

const AUDIO_CAP = 64;
const cache = new LRU<string, HTMLAudioElement>(AUDIO_CAP, (_k, audio) => {
  try {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
  } catch {
    /* noop */
  }
});

let current: HTMLAudioElement | null = null;
let sequencePlaying = false;

export function audioFor(src: string | undefined | null): HTMLAudioElement | null {
  if (!src) return null;
  // Story JSON paths are relative (e.g. "audio/story_1/s0.mp3").
  // Prepend the base path so the request hits the right URL on Project Pages.
  const url = src.startsWith('/') || /^https?:\/\//.test(src) ? src : `${base}/${src}`;
  let a = cache.get(url);
  if (!a) {
    a = new Audio(url);
    a.preload = 'auto';
    cache.set(url, a);
  }
  return a;
}

export function stopCurrent(): void {
  if (current) {
    try {
      current.pause();
      current.currentTime = 0;
    } catch {
      /* noop */
    }
    current = null;
  }
  sequencePlaying = false;
}

export function isSequencePlaying(): boolean {
  return sequencePlaying;
}

export function setSequencePlaying(v: boolean): void {
  sequencePlaying = v;
}

export function playOnce(src: string | null | undefined, opts: { onEnd?: () => void } = {}): void {
  const a = audioFor(src);
  if (!a) return;
  stopCurrent();
  current = a;
  a.onended = () => {
    current = null;
    opts.onEnd?.();
  };
  try {
    a.currentTime = 0;
  } catch {
    /* noop */
  }
  a.play().catch(() => {
    /* user-gesture restriction */
  });
}
