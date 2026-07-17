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

// Dans l'app, le backend FastAPI sert les pages d'écran et l'API sur 8001 ;
// dans le navigateur, Vite fait proxy → chemins relatifs.
export const BACKEND_BASE = isTauri ? 'http://127.0.0.1:8001' : ''

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
