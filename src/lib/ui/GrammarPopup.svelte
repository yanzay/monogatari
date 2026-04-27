<script lang="ts">
  import type { GrammarPoint } from '$lib/data/types';
  import { isGrammarEntryIncomplete } from '$lib/util/grammar';

  interface Props {
    gp: GrammarPoint;
  }
  let { gp }: Props = $props();
  let incomplete = $derived(isGrammarEntryIncomplete(gp));
</script>

{#if incomplete}
  <div class="badge-warn" title="Definition is missing — please fix data/grammar_state.json">
    ⚠ Definition incomplete
  </div>
{/if}
<div class="popup-grammar-title">{gp.title || gp.id}</div>
<div class="popup-grammar-short">{gp.short || '(no short description)'}</div>
<hr class="popup-divider" />
<div class="popup-grammar-long">{gp.long || '(no long description)'}</div>
{#if gp.genki_ref}<div class="popup-grammar-ref">Genki {gp.genki_ref}</div>{/if}
{#if gp.prerequisites?.length}
  <div class="popup-grammar-ref" style="margin-top:0.4rem;">
    Requires: {gp.prerequisites.join(', ')}
  </div>
{/if}

<style>
  .popup-grammar-title {
    font-family: var(--font-jp);
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.4rem;
  }
  .popup-grammar-short {
    font-size: 0.92rem;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
    font-style: italic;
  }
  .popup-grammar-long {
    font-size: 0.88rem;
    line-height: 1.65;
    color: var(--text);
    margin-bottom: 0.5rem;
  }
  .popup-grammar-ref {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-light);
  }
  .popup-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 0.85rem 0;
  }
</style>
