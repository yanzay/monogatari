/* Shared types describing the on-disk data shapes consumed by the reader. */

/* ── Vocab (sharded) ─────────────────────────────────────────────── */

export interface VocabIndex {
  version: number;
  generated_at?: string;
  shard_bits: number;
  shard_count: number;
  next_word_id?: string;
  last_story_id?: number;
  n_words: number;
  words: VocabIndexRow[];
}

export interface VocabIndexRow {
  id: string;
  shard: string;
  surface: string;
  kana: string;
  reading: string;
  short_meaning: string;
  first_story?: number | string;
  occurrences: number;
}

export interface VocabShard {
  version: number;
  shard: string;
  words: Record<string, Word>;
}

export interface Word {
  id: string;
  surface: string;
  kana: string;
  reading: string;
  pos: string;
  meanings: string[];
  first_story?: number | string;
  occurrences?: number;
  notes?: string;
  last_seen_story?: number | string;
  verb_class?: string;
  adj_class?: string;
  grammar_tags?: string[];
}

/* Legacy monolithic vocab state — still parsed if encountered. */
export interface VocabStateLegacy {
  version: number;
  updated_at?: string;
  last_story_id?: number;
  next_word_id?: string;
  words: Record<string, Word>;
}

/* ── Grammar ─────────────────────────────────────────────────────── */

export interface GrammarState {
  version: number;
  points: Record<string, GrammarPoint>;
}

export interface GrammarPoint {
  id: string;
  title?: string;
  short?: string;
  long?: string;
  genki_ref?: string;
  prerequisites?: string[];
  /**
   * The story id where this grammar point is first introduced. `null`
   * (or missing) means the learner has not yet encountered it in the
   * corpus — useful for filtering the grammar tab to "seen so far".
   *
   * Phase A derive-on-read (2026-05-01): this field is NO LONGER stored
   * on `data/grammar_state.json`. It is derived from corpus first-use
   * by `pipeline/build_grammar_attributions.py` (writes
   * `static/data/grammar_attributions.json`) and joined onto each point
   * by `loadGrammar()` in `corpus.ts`. Consumers should keep reading it
   * via `gp.intro_in_story` — the join is transparent.
   */
  intro_in_story?: number | null;
  /**
   * The most recent story id in which this grammar point appears.
   * Same provenance as `intro_in_story`: derived from corpus, joined
   * by `loadGrammar()`. Null/undefined for points never used.
   */
  last_seen_story?: number | null;
  _needs_review?: boolean;
}

/**
 * Server-side projection of derived grammar attributions. Lives at
 * `static/data/grammar_attributions.json` and is fetched by
 * `loadGrammar()` to populate `intro_in_story` / `last_seen_story` on
 * every grammar point. See `pipeline/build_grammar_attributions.py`
 * for the producer side.
 */
export interface GrammarAttributionsManifest {
  version: number;
  generated_at?: string;
  n_introduced: number;
  attributions: Record<
    string,
    { intro_in_story: number | null; last_seen_story: number | null }
  >;
}

export interface GrammarExamplesIndex {
  version: number;
  generated_at?: string;
  max_per_point: number;
  examples: Record<string, GrammarExample[]>;
}

export interface GrammarExample {
  story_id: number;
  sentence_idx: number;
  jp: string;
  gloss_en: string;
}

/* ── Stories ─────────────────────────────────────────────────────── */

export interface Story {
  story_id: number;
  title: { jp: string; en: string; tokens?: Token[]; r?: string; word_id?: string };
  new_words: string[];
  new_grammar: string[];
  all_words_used?: string[];
  sentences: Sentence[];
  word_audio?: Record<string, string>;
}

export interface Sentence {
  idx?: number;
  tokens: Token[];
  gloss_en: string;
  audio?: string;
}

export interface Token {
  t: string;
  r?: string;
  role?: 'content' | 'punct' | 'function' | string;
  word_id?: string;
  grammar_id?: string;
  is_new?: boolean;
  inflection?: { form: string; base: string; grammar_id: string };
}

/* ── Manifest (paginated v2; v1 still supported for compat) ──────── */

export interface StoryManifestEntry {
  story_id: number;
  path: string;
  title_jp?: string;
  title_en?: string;
  n_sentences?: number;
  n_content_tokens?: number;
  n_new_words?: number;
  n_new_grammar?: number;
  has_audio?: boolean;
}

export interface StoryManifestRoot {
  version: number;
  generated_at?: string;
  n_stories?: number;
  page_size?: number;
  pages?: StoryManifestPageSummary[];
  /** Legacy v1 OR small-corpus inline rows. */
  stories?: StoryManifestEntry[];
}

export interface StoryManifestPageSummary {
  page: number;
  path: string;
  first_story_id: number | null;
  last_story_id: number | null;
  n_stories: number;
}

export interface StoryManifestPagePayload {
  version: number;
  page: number;
  page_size: number;
  stories: StoryManifestEntry[];
}
