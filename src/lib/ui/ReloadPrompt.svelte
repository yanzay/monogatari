<script lang="ts">
  /**
   * Service-worker registration + "update available" toast.
   *
   * The PWA plugin is configured with `registerType: 'prompt'` and
   * `injectRegister: false`, which means *this* component is responsible
   * for actually registering the SW and reacting to updates.
   *
   * Behaviour:
   *  - On mount, register the SW.
   *  - Poll for updates every 60 s (default vite-plugin-pwa SW only checks
   *    on `pagehide`/period; an explicit poll keeps long-lived tabs fresh).
   *  - When an update is available, show a small toast at the bottom-right
   *    with [Reload] / [Later] buttons.
   *  - Reload calls updateSW(true) which messages the waiting SW to
   *    skipWaiting + reloads the page so the user lands on the new shell.
   *
   * Without this component, the SW would silently update on next *cold*
   * load only, leaving open tabs on the old shell indefinitely. That's
   * what happened with the library layout fix.
   */
  import { onMount } from 'svelte';

  let needRefresh = $state(false);
  let updateSW: ((reload?: boolean) => Promise<void>) | null = null;

  onMount(async () => {
    if (typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator)) return;

    try {
      // Dynamic import so the bundle doesn't hard-fail in unit tests.
      const { registerSW } = await import('virtual:pwa-register');
      updateSW = registerSW({
        immediate: true,
        onNeedRefresh() {
          needRefresh = true;
        },
        onRegisteredSW(_swUrl, registration) {
          // Poll for new SW versions every 60 s on long-lived tabs.
          if (registration) {
            setInterval(() => {
              registration.update().catch(() => {});
            }, 60_000);
          }
        },
      });
    } catch (e) {
      // virtual:pwa-register is not available in dev or in tests; ignore.
      console.debug('PWA register skipped:', e);
    }
  });

  function reload() {
    // Best-effort: ask the waiting SW to skip waiting (so the new
    // shell takes over) AND immediately force a hard reload. We don't
    // wait for the SW handshake — if the SW is buggy, the reload
    // alone still gets the user a fresh page from cache/network.
    try {
      updateSW?.(false);
    } catch {
      /* ignore */
    }
    if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
      // Tell every waiting SW (in case more than one is queued) to skip.
      navigator.serviceWorker.getRegistrations().then((regs) => {
        for (const r of regs) r.waiting?.postMessage({ type: 'SKIP_WAITING' });
      }).catch(() => {});
    }
    // Hard navigate — the most reliable way to get the new shell.
    setTimeout(() => window.location.reload(), 50);
  }

  function dismiss() {
    needRefresh = false;
  }
</script>

{#if needRefresh}
  <div class="reload-prompt" role="status" aria-live="polite">
    <span class="reload-prompt-text">A new version is available.</span>
    <div class="reload-prompt-actions">
      <button class="nav-action-btn" onclick={reload}>Reload</button>
      <button class="nav-action-btn" onclick={dismiss}>Later</button>
    </div>
  </div>
{/if}

<style>
  .reload-prompt {
    position: fixed;
    bottom: 1.2rem;
    right: 1.2rem;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.7rem 0.9rem;
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
    max-width: 18rem;
    font-size: 0.78rem;
    color: var(--text);
  }
  .reload-prompt-text {
    line-height: 1.3;
  }
  .reload-prompt-actions {
    display: flex;
    gap: 0.4rem;
  }
</style>
