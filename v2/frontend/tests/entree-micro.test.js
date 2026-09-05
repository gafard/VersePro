import test from 'node:test'
import assert from 'node:assert/strict'
import { useStore } from '../src/store.js'

// LE BUG QUE CES TESTS FERMENT.
//
// Journal du poste macOS, 9 août : le micro « actif », des blocs audio reçus
// par le backend toutes les 43 ms, Deepgram puis Nemotron mis à contribution
// deux minutes chacun — zéro mot transcrit. Le flux existait et ne contenait
// rien.
//
// L'ancien refreshAudioDevices retombait sur `inputs[0]` : le PREMIER
// périphérique énuméré, pas l'entrée par défaut du système. Sur ce Mac le
// premier est « Micro de "iPhone" » (Continuité), le micro intégré arrive
// second. Le premier démarrage ouvrait le défaut système et tout marchait ;
// ce rafraîchissement inscrivait ensuite l'iPhone dans l'état, et le
// démarrage SUIVANT le rouvrait avec `deviceId: { exact }`. Téléphone
// verrouillé : un flux muet, et rien à l'écran pour le dire.

const entrees = [
  { kind: 'audioinput', deviceId: 'iphone-continuite', label: 'Micro de « iPhone »' },
  { kind: 'audioinput', deviceId: 'macbook-integre', label: 'Micro MacBook Pro' }
]

// `navigator` est en lecture seule sur Node : on redéfinit la propriété.
function simulerPeripheriques(liste) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { mediaDevices: { enumerateDevices: async () => liste } }
  })
  return () => {
    if (original) Object.defineProperty(globalThis, 'navigator', original)
    else delete globalThis.navigator
  }
}

test('aucune entrée micro n’est choisie à la place de l’opérateur', async () => {
  const restaurer = simulerPeripheriques(entrees)
  useStore.setState({ selectedAudioDeviceId: '' })

  await useStore.getState().refreshAudioDevices()

  assert.equal(
    useStore.getState().selectedAudioDeviceId,
    '',
    'une chaîne vide signifie « entrée par défaut du système » : c’est le bon défaut'
  )
  assert.equal(useStore.getState().audioDevices.length, 2)
  restaurer()
})

test('un choix explicite toujours présent est conservé', async () => {
  const restaurer = simulerPeripheriques(entrees)
  useStore.setState({ selectedAudioDeviceId: 'macbook-integre' })

  await useStore.getState().refreshAudioDevices()

  assert.equal(useStore.getState().selectedAudioDeviceId, 'macbook-integre')
  restaurer()
})

test('un micro choisi puis débranché repart au défaut système', async () => {
  const restaurer = simulerPeripheriques(entrees)
  useStore.setState({ selectedAudioDeviceId: 'table-de-mixage-absente' })

  await useStore.getState().refreshAudioDevices()

  assert.equal(
    useStore.getState().selectedAudioDeviceId,
    '',
    'sinon getUserMedia échoue sur `exact` et le bouton micro reste mort'
  )
  restaurer()
})

test('le silence prolongé du micro est un état affiché, pas un silence de plus', async () => {
  const source = await import('node:fs/promises')
    .then((fs) => fs.readFile(new URL('../src/components/LiveDetection.jsx', import.meta.url), 'utf8'))

  assert.match(source, /micSilent/, 'la console doit lire l’état de silence')
  assert.match(
    source,
    /Aucun signal sur l’entrée micro/,
    'le journal de transcription doit nommer la panne au lieu de dire « en attente de parole »'
  )
})
