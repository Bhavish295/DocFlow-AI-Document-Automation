import * as esbuild from 'esbuild'
import fs from 'fs'
import path from 'path'
import { fileURLToPath, pathToFileURL } from 'url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outfile = path.join(root, 'scripts', `.review-intel-verify-${process.pid}.cjs`)

await esbuild.build({
  absWorkingDir: root,
  entryPoints: ['scripts/reviewIntelligenceChecks.jsx'],
  bundle: true,
  format: 'cjs',
  platform: 'node',
  packages: 'external',
  outfile,
  jsx: 'automatic',
  plugins: [
    {
      name: 'empty-css',
      setup(build) {
        build.onLoad({ filter: /\.css$/ }, () => ({ contents: '', loader: 'js' }))
      },
    },
  ],
})

try {
  await import(pathToFileURL(outfile).href)
} finally {
  fs.rmSync(outfile, { force: true })
}
