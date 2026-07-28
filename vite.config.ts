import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // GitHub Pages injects /global-trust-safety-dashboard/ from the repository name.
  base: process.env.VITE_BASE_PATH || '/',
})
