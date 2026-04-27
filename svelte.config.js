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
    router: {
      type: 'hash', // GH Pages can't do SPA URL rewrites; hash routing sidesteps it
    },
    serviceWorker: {
      register: false, // we use vite-plugin-pwa instead
    },
    alias: {
      $lib: 'src/lib',
    },
  },
};

export default config;
