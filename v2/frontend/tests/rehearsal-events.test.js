import test from 'node:test'
import assert from 'node:assert/strict'
import { rehearsalResults } from '../src/components/preparation/rehearsal-events.js'

test('une phrase audio garde tous ses passages dans le bilan', () => {
  const packet = {
    text: 'Lisons le psaume vingt-trois puis Romains huit vingt-huit',
    audio_seconds: 20,
    candidate: { reference: 'Psaumes 23:1', references_multiples: [{reference: 'Romains 8:28'}] },
  }
  const rows = rehearsalResults(packet)
  assert.deepEqual(rows.map(row => row.candidate.reference), ['Psaumes 23:1', 'Romains 8:28'])
  assert.equal(rows[1].audio_seconds, 20)
  assert.equal(packet.candidate.references_multiples.length, 1)
})

test('une fin de ponctuation ne masque pas un résultat ; une vraie annonce reste au bilan', () => {
  assert.deepEqual(rehearsalResults({text: '.', candidate: null}), [])
  assert.equal(rehearsalResults({text: 'Rendez-vous à dix-huit heures.', candidate: null}).length, 1)
})
