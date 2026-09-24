import test from 'node:test'
import assert from 'node:assert/strict'
import { fusionnerAvisIA, meriteAvisIA, libelleIA } from '../src/runtime/avis-ia.js'

const r = (reference, extra = {}) => ({ reference, ...extra })

test("l'avis de l'IA ne déplace pas la sélection du régisseur", () => {
  const anciens = [r('Hébreux 13:12'), r('Lévitique 9:18'), r('Néhémie 8:16')]
  const nouveaux = [r('Exode 12:7', { source: 'ai' }), ...anciens]

  // Le régisseur était descendu sur Lévitique 9:18 : il y reste.
  assert.deepEqual(fusionnerAvisIA(anciens, nouveaux, 1).activeIndex, 2)
  // Resté en tête : il voit la proposition de l'IA en tête.
  assert.deepEqual(fusionnerAvisIA(anciens, nouveaux, 0).activeIndex, 0)
})

test('un élément disparu de la nouvelle liste ramène en tête', () => {
  const anciens = [r('A'), r('B')]
  assert.equal(fusionnerAvisIA(anciens, [r('C')], 1).activeIndex, 0)
  assert.deepEqual(fusionnerAvisIA(anciens, null, 1).results, [])
})

test("seule une description interroge l'IA", () => {
  for (const reference of ['Jean 3:16', 'jean 3 16', '1 Co 13:4', 'Ps 23', 'Rm 8:28-30', 'amour']) {
    assert.equal(meriteAvisIA(reference), false, reference)
  }
  for (const description of ['le fils prodigue', 'Jonas dans le poisson', 'la Pentecôte et les langues de feu']) {
    assert.equal(meriteAvisIA(description), true, description)
  }
})

test("le libellé dit d'où vient la proposition", () => {
  assert.equal(libelleIA(r('Exode 12:7', { source: 'ai' })), 'Suggestion IA — à relire')
  assert.equal(libelleIA(r('Luc 15:20', { ia_confirme: true })), 'Confirmé par l’IA')
  assert.equal(libelleIA(r('Luc 15:20')), '')
})
