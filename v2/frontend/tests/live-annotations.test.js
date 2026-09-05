import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const liveDetectionPath = new URL('../src/components/LiveDetection.jsx', import.meta.url)

test('le surlignage live est rendu dans le panneau à l’antenne', async () => {
  const source = await readFile(liveDetectionPath, 'utf8')
  const onAirPanel = source.slice(
    source.indexOf('{/* Section ON AIR */}'),
    source.indexOf('{/* Section Journal de transcription */}')
  )

  assert.match(onAirPanel, /Surlignage Live/)
  assert.match(onAirPanel, /live-annotation-toolbar--onair/)
  assert.match(onAirPanel, /handleTextSelection\(event, onAirSelectionKey\)/)
  assert.match(onAirPanel, /renderSelectedVerseText\(onAirDisplay\.text, onAirSelectedText\)/)
  assert.match(onAirPanel, /sendLiveAnnotation\('highlight'\)/)
  assert.match(onAirPanel, /sendLiveAnnotation\('underline'\)/)
  assert.match(onAirPanel, /sendLiveAnnotation\('circle'\)/)
})

test('la file affiche la carte synthétique à l’antenne même sans détection en attente', async () => {
  const source = await readFile(liveDetectionPath, 'utf8')
  assert.match(source, /displayQueue\.length === 0/)
  assert.doesNotMatch(source, /projectionQueue\.length === 0 \? \(/)
})
