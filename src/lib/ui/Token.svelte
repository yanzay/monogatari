<script lang="ts">
  import type { Token } from '$lib/data/types';

  interface Props {
    tok: Token;
    isFirstInStory?: boolean;
    onWord?: (wordId: string, tok: Token) => void;
    onGrammar?: (grammarId: string) => void;
  }
  let { tok, isFirstInStory = false, onWord, onGrammar }: Props = $props();

  function clickToken() {
    if (tok.word_id && onWord) onWord(tok.word_id, tok);
    else if (tok.grammar_id && onGrammar) onGrammar(tok.grammar_id);
  }

  let clickable = $derived(!!(tok.word_id || tok.grammar_id) && tok.role !== 'punct');
</script>

{#if tok.role === 'punct'}
  <span class="token" data-role="punct">{tok.t}</span>
{:else if clickable}
  <!--
    Clickable tokens use a real <button> for keyboard + a11y. The ruby
    annotation, if any, lives inside the button so native focus/click
    semantics work without ARIA hacks.
  -->
  <button
    type="button"
    class="token clickable"
    data-role={tok.role}
    data-new={isFirstInStory && tok.is_new ? 'true' : undefined}
    onclick={clickToken}
    lang="ja"
  >
    {#if tok.r}
      <ruby>{tok.t}<rt>{tok.r}</rt></ruby>
    {:else}
      {tok.t}
    {/if}
  </button>
{:else if tok.r}
  <ruby class="token" data-role={tok.role} lang="ja">{tok.t}<rt>{tok.r}</rt></ruby>
{:else}
  <span class="token" data-role={tok.role} lang="ja">{tok.t}</span>
{/if}
