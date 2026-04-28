import { base } from '$app/paths';
import { LRU } from '$lib/util/lru';
import type {
  Story,
  StoryManifestRoot,
  StoryManifestPagePayload,
  GrammarState,
  GrammarExamplesIndex,
  VocabIndex,
  VocabIndexRow,
  VocabShard,
  VocabStateLegacy,
  Word,
} from './types';

/* ── Boot-time singletons ────────────────────────────────────────── */
let vocabIndexPromise: Promise<VocabIndex> | null = null;
let grammarPromise: Promise<GrammarState> | null = null;
let manifestPromise: Promise<StoryManifestRoot> | null = null;
let grammarExamplesPromise: Promise<GrammarExamplesIndex> | null = null;

async function fetchJSON<T>(path: string): Promise<T> {
  const url = `${base}${path}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return (await r.json()) as T;
}

/* ── Vocab ───────────────────────────────────────────────────────── */

/**
 * Load the lightweight vocab index. If the sharded build (data/vocab/index.json)
 * is unavailable we fall back to the legacy monolithic data/vocab_state.json
 * and synthesize an in-memory index — preserves old deploys during rollout.
 */
export function loadVocabIndex(): Promise<VocabIndex> {
  if (vocabIndexPromise) return vocabIndexPromise;
  vocabIndexPromise = (async () => {
    try {
      return await fetchJSON<VocabIndex>('/data/vocab/index.json');
    } catch {
      const legacy = await fetchJSON<VocabStateLegacy>('/data/vocab_state.json');
      const rows: VocabIndexRow[] = Object.values(legacy.words).map((w) => ({
        id: w.id,
        shard: '__legacy__',
        surface: w.surface,
        kana: w.kana,
        reading: w.reading,
        short_meaning: w.meanings?.[0] ?? '',
        first_story: w.first_story,
        occurrences: w.occurrences ?? 0,
      }));
      // Stash full records so getWord() can serve them.
      legacyWordsCache = legacy.words;
      return {
        version: legacy.version,
        generated_at: legacy.updated_at,
        shard_bits: 0,
        shard_count: 1,
        next_word_id: legacy.next_word_id,
        last_story_id: legacy.last_story_id,
        n_words: rows.length,
        words: rows,
      };
    }
  })();
  return vocabIndexPromise;
}

let legacyWordsCache: Record<string, Word> | null = null;
const shardCache = new LRU<string, Promise<VocabShard>>(64);
const wordCache = new LRU<string, Word>(2048);

/**
 * Returns full word detail. Cheap if the word is in cache; otherwise fetches
 * the appropriate shard once and indexes its words.
 */
export async function getWord(wordId: string): Promise<Word | null> {
  const hit = wordCache.get(wordId);
  if (hit) return hit;
  if (legacyWordsCache && legacyWordsCache[wordId]) {
    wordCache.set(wordId, legacyWordsCache[wordId]);
    return legacyWordsCache[wordId];
  }
  const idx = await loadVocabIndex();
  const row = idx.words.find((r) => r.id === wordId);
  if (!row) return null;
  if (row.shard === '__legacy__') return null; // shouldn't happen — covered above
  const shardPromise =
    shardCache.get(row.shard) ??
    (() => {
      const p = fetchJSON<VocabShard>(`/data/vocab/shards/${row.shard}.json`);
      shardCache.set(row.shard, p);
      return p;
    })();
  const shard = await shardPromise;
  for (const [wid, w] of Object.entries(shard.words)) {
    wordCache.set(wid, w);
  }
  return shard.words[wordId] ?? null;
}

/** Synchronous lookup against in-memory caches (returns null if not yet loaded). */
export function getWordSync(wordId: string): Word | null {
  return wordCache.get(wordId) ?? legacyWordsCache?.[wordId] ?? null;
}

/* ── Grammar ─────────────────────────────────────────────────────── */

export function loadGrammar(): Promise<GrammarState> {
  if (!grammarPromise) grammarPromise = fetchJSON<GrammarState>('/data/grammar_state.json');
  return grammarPromise;
}

export function loadGrammarExamples(): Promise<GrammarExamplesIndex> {
  if (!grammarExamplesPromise) {
    grammarExamplesPromise = fetchJSON<GrammarExamplesIndex>('/data/grammar_examples.json').catch(
      (): GrammarExamplesIndex => ({
        version: 1,
        max_per_point: 0,
        examples: {},
      }),
    );
  }
  return grammarExamplesPromise;
}

/* ── Manifest (paginated v2 + legacy v1) ─────────────────────────── */

export function loadManifest(): Promise<StoryManifestRoot> {
  if (!manifestPromise) manifestPromise = fetchJSON<StoryManifestRoot>('/stories/index.json');
  return manifestPromise;
}

const manifestPageCache = new LRU<number, Promise<StoryManifestPagePayload>>(8);

/**
 * Resolve a single manifest page by 1-based page index.
 * Returns null if the page doesn't exist.
 */
export async function loadManifestPage(page: number): Promise<StoryManifestPagePayload | null> {
  const root = await loadManifest();
  // v1 / inline-small-corpus path: synthesize a single-page payload.
  if (!root.pages || !root.pages.length) {
    if (root.stories && page === 1) {
      return {
        version: root.version ?? 1,
        page: 1,
        page_size: root.stories.length,
        stories: root.stories,
      };
    }
    return null;
  }
  const summary = root.pages[page - 1];
  if (!summary) return null;
  const cached = manifestPageCache.get(page);
  if (cached) return cached;
  const p = fetchJSON<StoryManifestPagePayload>(`/${summary.path}`);
  manifestPageCache.set(page, p);
  return p;
}

export async function manifestPageCount(): Promise<number> {
  const root = await loadManifest();
  if (root.pages?.length) return root.pages.length;
  if (root.stories?.length) return 1;
  return 0;
}

export async function manifestStoryCount(): Promise<number> {
  const root = await loadManifest();
  if (typeof root.n_stories === 'number') return root.n_stories;
  if (root.pages?.length) return root.pages.reduce((acc, p) => acc + p.n_stories, 0);
  return root.stories?.length ?? 0;
}

/* ── Stories (LRU-cached) ────────────────────────────────────────── */

const storyCache = new LRU<number, Promise<Story | null>>(32);

export function loadStoryById(id: number): Promise<Story | null> {
  if (!id) return Promise.resolve(null);
  const cached = storyCache.get(id);
  if (cached) return cached;
  const p = (async () => {
    try {
      const story = await fetchJSON<Story>(`/stories/story_${id}.json`);
      return story ? decorateWithAudioPaths(story) : null;
    } catch {
      return null;
    }
  })();
  storyCache.set(id, p);
  return p;
}

/**
 * Story JSON files don't carry audio paths today (the legacy reader
 * derived them by convention). Backfill them here so the rest of the
 * app can treat per-sentence and per-word audio as first-class data.
 *
 * Convention (matches what pipeline/audio_builder.py emits):
 *   - Per-sentence: audio/story_<id>/s<sentence_idx>.mp3
 *   - Per-word:     audio/story_<id>/w_<word_id>.mp3
 *
 * If the JSON already supplies a value (future pipeline change), we
 * keep it. We don't HEAD-probe to confirm files exist — non-existent
 * URLs will 503 from the SW, the play attempt will fail silently, and
 * the UI will continue working.
 */
function decorateWithAudioPaths(story: Story): Story {
  const sid = story.story_id;
  if (!sid) return story;
  const audioBase = `audio/story_${sid}`;

  const sentences = story.sentences.map((s) => {
    if (s.audio) return s;
    return { ...s, audio: `${audioBase}/s${s.idx}.mp3` };
  });

  let word_audio = story.word_audio ?? {};
  if (!story.word_audio || Object.keys(story.word_audio).length === 0) {
    // Word audio is decoupled from any story (since 2026-04-29) — files
    // live in a flat `audio/words/<id>.mp3` directory so they can be
    // played from any UI surface that opens a word popup, including
    // ones with no story context (vocab list, library, review queue).
    // We still synthesize the map per-story for any callers that
    // expect story.word_audio to be present.
    const wa: Record<string, string> = {};
    const seen = new Set<string>();
    for (const s of story.sentences) {
      for (const t of s.tokens) {
        if (t.word_id && !seen.has(t.word_id)) {
          seen.add(t.word_id);
          wa[t.word_id] = `audio/words/${t.word_id}.mp3`;
        }
      }
    }
    word_audio = wa;
  }

  return { ...story, sentences, word_audio };
}
