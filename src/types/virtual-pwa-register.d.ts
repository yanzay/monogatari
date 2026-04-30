/**
 * Ambient module declaration for vite-plugin-pwa's virtual entry. The
 * plugin would normally generate this at build time via its `client.d.ts`
 * helper, but we don't reference that helper from anywhere TypeScript
 * scans, so the dynamic `import('virtual:pwa-register')` in
 * `src/lib/ui/ReloadPrompt.svelte` resolves to `any` (and triggers
 * implicit-any errors on the callback parameters).
 *
 * Lives in its own `.d.ts` rather than alongside the SvelteKit
 * `declare global { namespace App {} }` block in `app.d.ts` because
 * having a peer `declare module` next to the kit globals would not be
 * picked up by svelte-check's compilation unit. A dedicated file is
 * unambiguous.
 *
 * Only the small surface our ReloadPrompt component touches is
 * declared. The plugin's full type surface is irrelevant here.
 */
declare module 'virtual:pwa-register' {
  export interface RegisterSWOptions {
    immediate?: boolean;
    onNeedRefresh?: () => void;
    onOfflineReady?: () => void;
    onRegisteredSW?: (
      swUrl: string,
      registration: ServiceWorkerRegistration | undefined,
    ) => void;
    onRegisterError?: (error: unknown) => void;
  }
  export function registerSW(
    options?: RegisterSWOptions,
  ): (reloadPage?: boolean) => Promise<void>;
}
