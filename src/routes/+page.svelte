<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';

  onMount(() => {
    goto(`${base}/read`, { replaceState: true });
  });
</script>

<p class="empty-state" style="padding:2rem;">Redirecting…</p>
