import test from 'node:test'
import assert from 'node:assert/strict'
import { MAX_RECONNECT_ATTEMPTS, reconnectDelay, shouldReconnect } from '../src/runtime/reconnect.js'

test('reconnectDelay applique un backoff exponentiel plafonné', () => {
  assert.equal(reconnectDelay(1), 750)
  assert.equal(reconnectDelay(2), 1500)
  assert.equal(reconnectDelay(7), 30000)
  assert.equal(reconnectDelay(50), 30000)
})

test('la reconnexion cesse hors direct, en manuel ou après le plafond', () => {
  assert.equal(shouldReconnect({ manual: false, listening: true, attempt: 1 }), true)
  assert.equal(shouldReconnect({ manual: true, listening: true, attempt: 1 }), false)
  assert.equal(shouldReconnect({ manual: false, listening: false, attempt: 1 }), false)
  assert.equal(shouldReconnect({ manual: false, listening: true, attempt: MAX_RECONNECT_ATTEMPTS }), false)
})

