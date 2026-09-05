export const MAX_RECONNECT_ATTEMPTS = 8

export function reconnectDelay(attempt) {
  const safeAttempt = Math.max(1, Number(attempt) || 1)
  return Math.min(30000, 750 * (2 ** Math.min(safeAttempt - 1, 6)))
}

export function shouldReconnect({ manual, listening, attempt }) {
  return !manual && Boolean(listening) && attempt < MAX_RECONNECT_ATTEMPTS
}

