import test from 'node:test'
import assert from 'node:assert/strict'
import { versetsVoisins } from '../src/runtime/verse-window.js'

const avant = (n, v) => n.filter((x) => x < v).length
const apres = (n, v) => n.filter((x) => x > v).length

test('au milieu du chapitre : cinq avant, cinq après', () => {
  const n = versetsVoisins(16, 36)
  assert.equal(n.length, 10)
  assert.equal(avant(n, 16), 5)
  assert.equal(apres(n, 16), 5)
  assert.ok(!n.includes(16), 'le verset à l’antenne ne se propose pas lui-même')
})

test('au PREMIER verset : dix en avant, aucun trou', () => {
  // Rien derrière le verset 1. Sans décalage, la moitié des boutons
  // n’existerait pas et le régisseur perdrait cinq raccourcis.
  const n = versetsVoisins(1, 36)
  assert.equal(n.length, 10)
  assert.equal(avant(n, 1), 0)
  assert.deepEqual(n, [2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
})

test('au DERNIER verset : dix en arrière', () => {
  const n = versetsVoisins(36, 36)
  assert.equal(n.length, 10)
  assert.equal(apres(n, 36), 0)
  assert.deepEqual(n, [26, 27, 28, 29, 30, 31, 32, 33, 34, 35])
})

test('près du bord, la fenêtre glisse sans jamais sortir du chapitre', () => {
  const n = versetsVoisins(3, 36)
  assert.equal(n.length, 10)
  assert.ok(Math.min(...n) >= 1)
  assert.ok(Math.max(...n) <= 36)
})

test('un chapitre trop court rend ce qu’il a, sans inventer', () => {
  // Psaumes 117 fait deux versets : proposer 117:7 enverrait la régie sur un
  // verset inexistant en plein culte.
  assert.deepEqual(versetsVoisins(1, 2), [2])
  assert.deepEqual(versetsVoisins(2, 2), [1])
})

test('entrées absurdes : aucune proposition plutôt qu’une fausse', () => {
  assert.deepEqual(versetsVoisins(0, 36), [])
  assert.deepEqual(versetsVoisins(40, 36), [])
  assert.deepEqual(versetsVoisins(1, 1), [])
  assert.deepEqual(versetsVoisins(undefined, 36), [])
  assert.deepEqual(versetsVoisins(5, undefined), [])
})
