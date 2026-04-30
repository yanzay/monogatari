<script lang="ts">
  import type { Token } from '$lib/data/types';

  interface Props {
    tok: Token;
    isFirstInStory?: boolean;
    onWord?: (wordId: string, tok: Token) => void;
    onGrammar?: (grammarId: string) => void;
  }
  let { tok, isFirstInStory = false, onWord, onGrammar }: Props = $props();

  function clickToken(e: MouseEvent | KeyboardEvent) {
    // Stop the click from bubbling up to the parent .sentence-wrap, which
    // also has an onclick that opens the sentence popup.
    e.stopPropagation();
    if (tok.word_id && onWord) onWord(tok.word_id, tok);
    else if (tok.grammar_id && onGrammar) onGrammar(tok.grammar_id);
  }

  function keyToken(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      clickToken(e);
    }
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
    onkeydown={keyToken}
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

<style>
  /*
   * Token styles — moved from app.css during the per-component
   * decomposition. Svelte hashes the selectors so they only match
   * elements rendered by Token.svelte (and components that compose
   * it like RubyHeader and SentencePopup, since they instantiate
   * <Token>).
   */

  /* Clickable tokens use a real <button>; ensure they flow as text. */
  button.token {
    display: inline;
  }
  button.token:has(> ruby) {
    display: inline;
  }

  .token {
    display: inline;
    cursor: default;
    border-radius: 3px;
    transition: background 0.12s;
  }
  ruby.token {
    display: ruby;
  }
  .token.clickable { cursor: pointer; }

  /* Clickable tokens are ALWAYS rendered as <button> (see template
   * above; the .clickable class only appears on the button branch).
   * Earlier styles also targeted span.token.clickable:hover and
   * ruby.token.clickable:hover defensively, but those selectors never
   * matched anything and svelte-check flagged them. */
  button.token.clickable:hover,
  button.token.clickable:hover ruby {
    background: var(--surface2);
  }

  /* Content tokens */
  .token[data-role='content'] { color: var(--text); }

  /* First occurrence in this story — solid red underline */
  .token[data-new='true'] {
    text-decoration: underline;
    text-decoration-color: var(--accent);
    text-decoration-style: solid;
    text-underline-offset: 5px;
  }

  /* Seen before — dotted grey underline */
  .token[data-role='content']:not([data-new='true']) {
    text-decoration: underline;
    text-decoration-color: var(--text-light);
    text-decoration-style: dotted;
    text-underline-offset: 5px;
  }

  /* Particles / aux */
  .token[data-role='particle'],
  .token[data-role='aux'] {
    text-decoration: none;
    color: var(--text-muted);
  }
  .token[data-role='particle'].clickable:hover,
  .token[data-role='aux'].clickable:hover {
    text-decoration: underline;
    text-decoration-color: var(--border);
    text-decoration-style: dotted;
    text-underline-offset: 5px;
  }

  /* Punctuation */
  .token[data-role='punct'] { color: var(--text-muted); cursor: default; }

  /* Furigana (ruby) — hidden by default, fade in on hover */
  ruby {
    display: ruby;
    ruby-align: center;
  }
  rt {
    display: rt;
    font-family: var(--font-jp);
    font-size: 0.5em;
    color: var(--text-muted);
    letter-spacing: 0.03em;
    opacity: 0;
    line-height: 0;
    transition: opacity 0.15s;
  }
  .token:hover rt,
  button.token:hover ruby rt {
    opacity: 1;
    line-height: 1.2;
  }
</style>
