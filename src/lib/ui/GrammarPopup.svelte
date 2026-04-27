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
