import { defineConfig } from 'vite';

export default defineConfig({
  base: '/admin/assets/tenants/',
  build: { outDir: 'src/agent_nexus_web/static/tenants', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
