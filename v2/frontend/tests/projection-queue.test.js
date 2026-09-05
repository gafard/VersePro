import test from 'node:test'
import assert from 'node:assert/strict'
import { useStore } from '../src/store.js'

const pending = {
  queueId: 'queue-1',
  reference: 'Jean 3:16',
  text: 'Car Dieu a tant aimé le monde',
  status: 'pending'
}

test('la file reste en attente quand le moteur refuse la projection', async () => {
  const originalFetch = globalThis.fetch
  const originalTimeout = globalThis.setTimeout
  globalThis.setTimeout = () => 0
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: 'Sortie indisponible' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } }
  )
  useStore.setState({ projectionQueue: [{ ...pending }], toasts: [] })

  const sent = await useStore.getState().projectVerseFromQueue(
    pending.queueId,
    pending.reference,
    pending.text
  )

  assert.equal(sent, false)
  assert.equal(useStore.getState().projectionQueue[0].status, 'pending')
  globalThis.fetch = originalFetch
  globalThis.setTimeout = originalTimeout
})

test('la file passe à projeté après accusé du moteur navigateur', async () => {
  const originalFetch = globalThis.fetch
  const originalTimeout = globalThis.setTimeout
  globalThis.setTimeout = () => 0
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      success: true,
      reference: pending.reference,
      text: pending.text,
      outputs: { browser: true }
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  )
  useStore.setState({ projectionQueue: [{ ...pending }], toasts: [] })

  const sent = await useStore.getState().projectVerseFromQueue(
    pending.queueId,
    pending.reference,
    pending.text
  )

  assert.equal(sent, true)
  assert.equal(useStore.getState().projectionQueue[0].status, 'projected')
  globalThis.fetch = originalFetch
  globalThis.setTimeout = originalTimeout
})

test('vider les détections ne touche pas au déroulé préparé', () => {
  const prepared = {
    id: 'prepared-1',
    reference: 'Romains 8:28',
    text: 'Toutes choses concourent au bien',
  }
  useStore.setState({
    projectionQueue: [{ ...pending }],
    preparedVerses: [prepared],
    toasts: [],
  })

  useStore.getState().clearDetectedVerses()

  assert.deepEqual(useStore.getState().projectionQueue, [])
  assert.deepEqual(useStore.getState().preparedVerses, [prepared])
})

test('le bouton suivant remplace la carte sans la projeter ni toucher au déroulé', () => {
  const pendingVerse = { ...pending, status: 'pending' }
  useStore.setState({ projectionQueue: [pendingVerse], preparedVerses: [], onAir: null, toasts: [] })

  useStore.getState().replaceQueuedVerse('queue-1', {
    reference: 'Jean 3:17',
    text: 'Dieu, en effet, n’a pas envoyé son Fils dans le monde pour qu’il juge le monde',
    version: 'LSG'
  })

  const state = useStore.getState()
  assert.equal(state.projectionQueue[0].reference, 'Jean 3:17')
  assert.equal(state.projectionQueue[0].status, 'pending')
  assert.equal(state.onAir, null)
  assert.deepEqual(state.preparedVerses, [])
})


test('une correction orale retire le candidat récent mais conserve ce qui a été projeté', () => {
  useStore.setState({projectionQueue: [
    {...pending, detectedAt: new Date().toISOString()},
    {...pending, queueId: 'projected', status: 'projected'},
    {...pending, queueId: 'old', detectedAt: new Date(Date.now()-60000).toISOString()},
  ]})
  useStore.getState().addToProjectionQueue({reference:'Jean 14:6', text:'Je suis le chemin', detection_method:'spoken_revision', requires_review:true, superseded_references:['Jean 3:16']})
  const rows=useStore.getState().projectionQueue
  assert.equal(rows[0].status,'rejected')
  assert.equal(rows[1].status,'projected')
  assert.equal(rows[2].status,'pending')
  assert.equal(rows[3].reference,'Jean 14:6')
  assert.equal(rows[3].requiresReview,true)
})
