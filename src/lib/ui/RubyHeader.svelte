<script lang="ts">
  import type { Story, Token } from '$lib/data/types';
  import TokenEl from './Token.svelte';

  interface Props {
    title: Story['title'];
    onWord?: (wordId: string, tok: Token) => void;
    onGrammar?: (grammarId: string) => void;
  }
  let { title, onWord, onGrammar }: Props = $props();

  let seen = $derived.by(() => {
    const set = new Set<string>();
    if (title.tokens) for (const t of title.tokens) if (t.word_id) set.add(t.word_id);
    return set;
  });

  function clickHeader() {
    if (title.word_id && onWord) onWord(title.word_id, { t: title.jp, r: title.r });
  }
</script>

{#if title.tokens}
  {#each title.tokens as tok, i (i)}
    <TokenEl
      {tok}
      isFirstInStory={!seen.has(tok.word_id ?? '__never__')}
      {onWord}
      {onGrammar}
    />
  {/each}
{:else if title.word_id && title.r}
  <button
    type="button"
    class="token clickable"
    data-role="content"
    onclick={clickHeader}
    lang="ja"
  >
    <ruby>{title.jp}<rt>{title.r}</rt></ruby>
  </button>
{:else if title.r}
  <ruby class="token" data-role="content" lang="ja">{title.jp}<rt>{title.r}</rt></ruby>
{:else}
  <span lang="ja">{title.jp}</span>
{/if}
