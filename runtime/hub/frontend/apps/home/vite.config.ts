import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Dev keeps Vite's default root-style asset paths.
  // Build uses a relative base so follow-on chunks/assets resolve from the
  // runtime script URL injected by JupyterHub templates via static_url(...).
  base: command === 'build' ? './' : '/',
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
}))
