import test from 'node:test'
import assert from 'node:assert/strict'
import { useStore } from '../src/store.js'

const searchResult = {
  reference: 'Jean 3:16',
  text: 'Car Dieu a tant aimé le monde',
  version: 'LSG'
}

test('Entrée peut préparer un verset sans le projeter', async () => {
  const originalFetch = globalThis.fetch
  const originalStorage = globalThis.localStorage
  const originalTimeout = globalThis.setTimeout
  const requests = []
  const saved = new Map()

  globalThis.setTimeout = () => 0
  globalThis.localStorage = {
    getItem: (key) => saved.get(key) || null,
    setItem: (key, value) => saved.set(key, value)
  }
  globalThis.fetch = async (url) => {
    requests.push(String(url))
    return new Response(
      JSON.stringify({ results: [searchResult] }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }
  useStore.setState({ preparedVerses: [], toasts: [], onAir: null })

  try {
    const prepared = await useStore.getState().prepareReference('Jn 3:16')

    assert.equal(prepared.reference, searchResult.reference)
    assert.equal(useStore.getState().preparedVerses.length, 1)
    assert.equal(useStore.getState().onAir, null)
    assert.match(requests[0], /\/api\/v1\/bible\/search\?/)
    // Préparer un verset le fait connaître au MOTEUR : le déroulé sert de
    // plan de prédication et départage les références mal entendues. Il ne
    // vivait avant que dans le navigateur.
    assert.ok(
      requests.some((url) => /\/api\/v1\/plan$/.test(url)),
      'le déroulé doit être transmis au moteur de détection'
    )
    // Ce que le test protège vraiment : préparer n'est pas projeter.
    assert.ok(
      !requests.some((url) => /\/references\/send/.test(url)),
      'préparer un verset ne doit jamais le projeter'
    )
    assert.match(saved.get('versepro_prepared_verses'), /Jean 3:16/)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalStorage
    globalThis.setTimeout = originalTimeout
  }
})

test('un verset préparé ne se projette qu’après action explicite', async () => {
  const originalFetch = globalThis.fetch
  const originalStorage = globalThis.localStorage
  const originalTimeout = globalThis.setTimeout
  const item = {
    id: 'prepared-1',
    ...searchResult,
    addedAt: new Date().toISOString(),
    lastProjectedAt: null
  }

  globalThis.setTimeout = () => 0
  globalThis.localStorage = { getItem: () => null, setItem: () => {} }
  globalThis.fetch = async (url) => {
    assert.match(String(url), /\/api\/v1\/references\/send/)
    return new Response(
      JSON.stringify({ success: true, ...searchResult, outputs: { browser: true } }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }
  useStore.setState({ preparedVerses: [item], toasts: [], onAir: null })

  try {
    const sent = await useStore.getState().projectPreparedVerse(item.id)

    assert.equal(sent, true)
    assert.equal(useStore.getState().onAir.reference, searchResult.reference)
    assert.ok(useStore.getState().preparedVerses[0].lastProjectedAt)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalStorage
    globalThis.setTimeout = originalTimeout
  }
})

test('la même référence n’est pas ajoutée deux fois au déroulé', async () => {
  const originalFetch = globalThis.fetch
  const originalTimeout = globalThis.setTimeout

  globalThis.setTimeout = () => 0
  globalThis.fetch = async () => new Response(
    JSON.stringify({ results: [searchResult] }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  )
  useStore.setState({ preparedVerses: [], toasts: [] })

  try {
    await useStore.getState().prepareReference('Jean 3:16')
    await useStore.getState().prepareReference('Jn 3:16')

    assert.equal(useStore.getState().preparedVerses.length, 1)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.setTimeout = originalTimeout
  }
})

test('la pastille du plan annonce ce que le MOTEUR a retenu', async () => {
  // Une entrée écrite à la main peut ne pas se parser. Afficher la longueur
  // de la liste donnerait au régisseur une confiance sans objet : le moteur
  // ne départagera les versets mal entendus que sur ce qu'il a compris.
  const originalFetch = globalThis.fetch
  const originalStorage = globalThis.localStorage
  const saved = new Map()
  globalThis.localStorage = {
    getItem: (key) => saved.get(key) || null,
    setItem: (key, value) => saved.set(key, value)
  }
  globalThis.fetch = async (url) => {
    const cible = String(url)
    const corps = /\/api\/v1\/plan$/.test(cible)
      ? { status: 'ok', count: 2 }          // 3 envoyées, 2 comprises
      : { results: [searchResult] }
    return new Response(JSON.stringify(corps), {
      status: 200, headers: { 'Content-Type': 'application/json' }
    })
  }
  useStore.setState({ preparedVerses: [], toasts: [], onAir: null, planCount: null })

  try {
    await useStore.getState().prepareReference('Jn 3:16')
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(useStore.getState().planCount, 2)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalStorage
  }
})
