import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const read = (path) => readFileSync(`${root}/${path}`, 'utf8')

const styles = read('src/styles.css')
const canvas = read('src/components/GraphCanvas.tsx')
const card = read('src/components/GraphCard.tsx')

assert.match(styles, /--bg:\s*#f7faf8/i, 'light graph background token is missing')
assert.match(styles, /--accent:\s*#5f9d7f/i, 'sage accent token is missing')
assert.match(styles, /prefers-reduced-motion/i, 'reduced-motion fallback is missing')
assert.match(styles, /@keyframes\s+node-reveal/i, 'node reveal animation is missing')
assert.match(styles, /graph-card\.is-selected[^}]*box-shadow/i, 'selected node halo is missing')
assert.match(canvas, /colorMode="light"/, 'React Flow must use light mode')
assert.match(canvas, /motionOrder/, 'graph node motion order hook is missing')
assert.match(card, /node-motion|graph-card/, 'graph card motion hook is missing')

console.log('Light theme contract passed')
