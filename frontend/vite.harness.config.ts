/** Build config for the media engine loopback harness (scripts/test_media_loopback.py). No catalog plugin. */
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: fileURLToPath(new URL('./src/media-harness', import.meta.url)),
  base: './',
  build: { outDir: process.env.MEDIA_HARNESS_OUT || fileURLToPath(new URL('./node_modules/.tmp/media-harness', import.meta.url)), emptyOutDir: true },
  logLevel: 'warn',
});
