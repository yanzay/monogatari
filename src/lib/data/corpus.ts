import { base } from '$app/paths';
import { LRU } from '$lib/util/lru';
import type { Story, StoryManifest, VocabState, GrammarState } from './types';

/* ── Boot-time singletons ────────────────────────────────────────── */
let vocabPromise: Promise<VocabState> | null = null;
let grammarPromise: Promise<GrammarState> | null = null;
let manifestPromise: Promise<StoryManifest> | null = null;

async function fetchJSON<T>(path: string): Promise<T> {
  const url = `${base}${path}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return (await r.json()) as T;
}

export function loadVocab(): Promise<VocabState> {
  if (!vocabPromise) vocabPromise = fetchJSON<VocabState>('/data/vocab_state.json');
  return vocabPromise;
}

export function loadGrammar(): Promise<GrammarState> {
  if (!grammarPromise) grammarPromise = fetchJSON<GrammarState>('/data/grammar_state.json');
  return grammarPromise;
}

export function loadManifest(): Promise<StoryManifest> {
  if (!manifestPromise) manifestPromise = fetchJSON<StoryManifest>('/stories/index.json');
  return manifestPromise;
}

/* ── Story cache (LRU, capped) ───────────────────────────────────── */
const storyCache = new LRU<number, Promise<Story | null>>(32);

export function loadStoryById(id: number): Promise<Story | null> {
  if (!id) return Promise.resolve(null);
  const cached = storyCache.get(id);
  if (cached) return cached;
  const p = (async () => {
    try {
      return await fetchJSON<Story>(`/stories/story_${id}.json`);
    } catch {
      return null;
    }
  })();
  storyCache.set(id, p);
  return p;
}
