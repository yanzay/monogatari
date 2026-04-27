<script lang="ts">
  import type { Sentence, Token } from '$lib/data/types';
  import { audioFor, playOnce } from '$lib/data/audio';
  import { popup } from '$lib/state/popup.svelte';
  import TokenEl from './Token.svelte';

  interface Props {
    sentence: Sentence;
    storyId: number;
    sentenceIdx: number;
  }
  let { sentence, storyId, sentenceIdx }: Props = $props();

  function onWord(wordId: string, tok: Token) {
    popup.openWord(wordId, tok);
  }
  function onGrammar(gid: string) {
    popup.openGrammar(gid);
  }
  function play() {
    if (!sentence.audio) return;
    playOnce(sentence.audio);
  }
</script>

<div class="popup-pos">Story {storyId} · Sentence {sentenceIdx + 1}</div>
{#if sentence.audio}
  <button class="btn-audio popup-audio-btn" onclick={play}>▶ play sentence</button>
{/if}
<hr class="popup-divider" />
<div class="popup-sentence-jp" lang="ja">
  {#each sentence.tokens as tok, ti (ti)}
    <TokenEl {tok} {onWord} {onGrammar} />
  {/each}
</div>
<hr class="popup-divider" />
<div class="popup-sentence-en">
  {sentence.gloss_en}
</div>

<style>
  .popup-pos {
    display: inline-block;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    background: var(--surface2);
    border-radius: 4px;
    padding: 0.1rem 0.45rem;
    color: var(--text-muted);
    margin-bottom: 0.65rem;
  }
  .popup-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 0.85rem 0;
  }
  .popup-sentence-jp {
    font-size: 1.1rem;
    line-height: 2;
  }
  .popup-sentence-en {
    font-style: italic;
    color: var(--text-muted);
  }
  .popup-audio-btn {
    margin-bottom: 0.5rem;
  }
</style>
