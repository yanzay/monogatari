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
  <button class="btn-audio" style="margin-bottom:0.5rem;" onclick={play}>▶ play sentence</button>
{/if}
<hr class="popup-divider" />
<div class="popup-sentence-jp" lang="ja" style="font-size:1.1rem;line-height:2;">
  {#each sentence.tokens as tok, ti (ti)}
    <TokenEl {tok} {onWord} {onGrammar} />
  {/each}
</div>
<hr class="popup-divider" />
<div class="popup-sentence-en" style="font-style:italic;color:var(--text-muted);">
  {sentence.gloss_en}
</div>
