/* Shared types describing the on-disk data shapes consumed by the reader. */

export interface VocabState {
  version: number;
  updated_at?: string;
  last_story_id?: number;
  next_word_id?: string;
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
  _needs_review?: boolean;
}

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

export interface StoryManifest {
  version: number;
  generated_at?: string;
  stories: StoryManifestEntry[];
}

export interface StoryManifestEntry {
  story_id: number;
  path: string;
  title_jp?: string;
  title_en?: string;
  n_sentences?: number;
  n_content_tokens?: number;
}
