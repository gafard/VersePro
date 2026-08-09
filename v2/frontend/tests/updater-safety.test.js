import test from 'node:test'
import assert from 'node:assert/strict'
import { useStore } from '../src/store.js'

test('la mise à jour est bloquée tant que le micro est ouvert', async () => {
  const originalTimeout = globalThis.setTimeout
  globalThis.setTimeout = () => 0
  useStore.setState({ isListening: true, onAir: null, toasts: [], desktopUpdateError: null })

  try {
    const installed = await useStore.getState().installDesktopUpdate()
    assert.equal(installed, false)
    assert.match(useStore.getState().desktopUpdateError, /arrêtez le micro/i)
  } finally {
    globalThis.setTimeout = originalTimeout
  }
})

test('la mise à jour est bloquée tant qu’un verset est à l’antenne', async () => {
  const originalTimeout = globalThis.setTimeout
  globalThis.setTimeout = () => 0
  useStore.setState({
    isListening: false,
    onAir: { reference: 'Jean 3:16', text: 'Car Dieu a tant aimé le monde' },
    toasts: [],
    desktopUpdateError: null
  })

  try {
    const installed = await useStore.getState().installDesktopUpdate()
    assert.equal(installed, false)
    assert.match(useStore.getState().desktopUpdateError, /à l’antenne/i)
  } finally {
    globalThis.setTimeout = originalTimeout
  }
})
