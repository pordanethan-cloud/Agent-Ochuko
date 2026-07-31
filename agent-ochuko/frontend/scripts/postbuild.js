import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const distDir = path.resolve(__dirname, '../dist')
const indexHtml = path.join(distDir, 'index.html')

if (fs.existsSync(indexHtml)) {
  // Routes that might be directly loaded or redirected to by external services (e.g. Google OAuth)
  const routes = ['auth/callback', 'login']
  routes.forEach(route => {
    const routeDir = path.join(distDir, route)
    fs.mkdirSync(routeDir, { recursive: true })
    fs.copyFileSync(indexHtml, path.join(routeDir, 'index.html'))
    console.log(`[postbuild] Created static entry for SPA route: /${route}/index.html (prevents Azure Blob Storage 404 response status)`)
  })
}
