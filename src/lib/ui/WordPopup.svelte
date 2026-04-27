<script lang="ts">
  import type { Word, Story, Token, GrammarState } from '$lib/data/types';
  import { audioFor } from '$lib/data/audio';
  import { learner } from '$lib/state/learner.svelte';

  interface Props {
    word: Word;
    tok?: Token;
    story: Story | null;
    grammar: GrammarState;
    onOpenGrammar: (gid: string) => void;
  }
  let { word, tok, story, grammar, onOpenGrammar }: Props = $props();

  let isNew = $derived(!!story?.new_words?.includes(word.id));
  let inflection = $derived(tok?.inflection);
  let audioSrc = $derived(story?.word_audio?.[word.id]);
  let srs = $derived(learner.state.srs?.[word.id]);
  let hasKanji = $derived(word.surface !== word.kana);

  $effect(() => {
    if (audioSrc && learner.state.prefs?.audio_autoplay) {
      const a = audioFor(audioSrc);
      try {
        a?.play();
      } catch {
        /* noop */
      }
    }
  });

  function playWord() {
    const a = audioFor(audioSrc);
    if (!a) return;
    try {
      a.currentTime = 0;
      a.play();
    } catch {
      /* noop */
    }
  }
</script>

{#if audioSrc}
  <button class="btn-audio" style="margin-bottom:0.5rem;" onclick={playWord}>▶ play word</button>
{/if}

{#if isNew}
  <div class="badge-new">New word</div>
{/if}

<div class="popup-word" lang="ja">
  {word.surface}{#if hasKanji}
    <span style="font-size:1.1rem;font-weight:400;color:var(--text-muted);margin-left:0.5rem;"
      >{word.kana}</span
    >
  {/if}
</div>
<div class="popup-reading"><span>/ {word.reading} /</span></div>
<div class="popup-pos">
  {word.pos}{#if word.verb_class} · {word.verb_class}{/if}{#if word.adj_class} · {word.adj_class}-adj{/if}
</div>
<div class="popup-meanings">{word.meanings.join('; ')}</div>

{#if inflection}
  <hr class="popup-divider" />
  <div class="popup-pos">inflection · {inflection.form}</div>
  <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:0.5rem;">
    Base form: <span lang="ja">{inflection.base}</span>
  </div>
  {#if grammar.points[inflection.grammar_id]}
    <div style="font-size:0.82rem;color:var(--text-muted);font-style:italic;">
      {grammar.points[inflection.grammar_id].short}
    </div>
  {/if}
{/if}

<hr class="popup-divider" />
<div class="popup-meta">
  <span>First seen: Story {word.first_story}</span>
  <span>Seen {word.occurrences ?? 0}×</span>
  {#if srs}<span>SRS: {srs.status}</span>{/if}
</div>

{#if word.grammar_tags?.length}
  <div>
    {#each word.grammar_tags as gid (gid)}
      {@const gp = grammar.points[gid]}
      {#if gp}
        <button
          class="popup-pos"
          style="cursor:pointer;background:none;border:none;padding:0;font:inherit;color:inherit;text-decoration:underline;"
          onclick={() => onOpenGrammar(gid)}>{gp.title}</button
        >
      {/if}
    {/each}
  </div>
{/if}
