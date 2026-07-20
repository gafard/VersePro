// Détection d'environnement partagée (navigateur vs application Tauri empaquetée).
// Robuste : basée sur le PROTOCOLE/hôte, pas sur window.__TAURI__ (qui n'existe
// que si withGlobalTauri est activé). Sans ça, toute la console était muette
// dans l'app (API, écrans, détection).
export const isTauri =
  typeof window !== 'undefined' && (
    typeof window.__TAURI__ !== 'undefined' ||
    typeof window.__TAURI_INTERNALS__ !== 'undefined' ||
    window.location.protocol === 'tauri:' ||
    window.location.hostname === 'tauri.localhost'
  )

// L'application empaquetée utilise un port dédié, volontairement distinct des
// ports de développement courants. Dans le navigateur, Vite continue de faire
// proxy vers le port choisi par VITE_BACKEND_PORT.
export const TAURI_BACKEND_PORT = '17871'
export const BACKEND_BASE = isTauri ? `http://127.0.0.1:${TAURI_BACKEND_PORT}` : ''
export const BACKEND_WS_BASE = isTauri ? `ws://127.0.0.1:${TAURI_BACKEND_PORT}` : ''

// Ouvre une URL EXTERNE (écran de projection sur le vidéoprojecteur). Sous Tauri,
// window.open est intercepté → on passe par le navigateur système via l'API
// shell ; sinon, fenêtre navigateur classique.
export function openExternal(url, features = 'width=1280,height=720,menubar=no,toolbar=no') {
  if (isTauri) {
    const shellOpen = window.__TAURI__?.shell?.open
    if (typeof shellOpen === 'function') {
      shellOpen(url)
      return
    }
  }
  window.open(url, '_blank', features)
}
