import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const dev = process.env.NODE_ENV !== 'production';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html', // SPA-style fallback (we use hash routing anyway)
      precompress: false,
      strict: false,
    }),
    paths: {
      // Project Pages: deployed at https://yanzay.github.io/monogatari/
      base: dev ? '' : '/monogatari',
      relative: false,
    },
    // Path-mode SPA. GH Pages can't do server-side rewrites, but we
    // generate a 404.html that mirrors index.html in the deploy
    // workflow, which makes deep-link navigation work for first-time
    // visits (the SW handles subsequent navigations from cache).
    serviceWorker: {
      register: false, // we use vite-plugin-pwa instead
    },
    alias: {
      $lib: 'src/lib',
    },
  },
};

export default config;
