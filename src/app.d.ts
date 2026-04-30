// See https://svelte.dev/docs/kit/types#app
//
// Ambient declarations for build-time virtual modules (e.g.
// `virtual:pwa-register`) live in `src/types/*.d.ts`, not here, so the
// kit-managed namespace block stays focused.
declare global {
  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

export {};
