import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// Polices auto-hébergées (contrainte produit : fonctionne sans internet)
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/700.css'
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import './tokens.css'
import './index.css'
import { BACKEND_BASE, BACKEND_WS_BASE, isTauri } from './env.js'

// Sous Tauri, le frontend est servi en tauri://localhost (ou https://tauri.localhost
// sous Windows) : les appels relatifs (/api, /ws) sont réécrits vers le backend
// local. Détection robuste par protocole/hôte (voir env.js) — sans quoi TOUTE
// la console était muette dans l'app empaquetée (téléchargements, écrans, détection).
async function installBackendTransport() {
  let sessionToken = import.meta.env.VITE_API_TOKEN || ''
  if (isTauri) {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      sessionToken = await invoke('obtenir_jeton_session')
    } catch (error) {
      console.error('Jeton de session Tauri indisponible', error)
    }
  }

  const origFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    let target = input
    if (isTauri && typeof target === 'string' && target.startsWith('/')) {
      target = BACKEND_BASE + target
    }
    const url = typeof target === 'string' ? target : target?.url || ''
    const isBackend = url.startsWith(BACKEND_BASE || '/') ||
      (isTauri && url.startsWith(BACKEND_BASE))
    if (!sessionToken || !isBackend) return origFetch(target, init)
    const headers = new Headers(init?.headers || (target instanceof Request ? target.headers : undefined))
    headers.set('Authorization', `Bearer ${sessionToken}`)
    return origFetch(target, { ...init, headers })
  }

  const OrigWebSocket = window.WebSocket
  window.WebSocket = class extends OrigWebSocket {
    constructor(url, protocols) {
      if (isTauri && typeof url === 'string') {
        if (url.startsWith('/')) url = BACKEND_WS_BASE + url
        else url = url.replace(/^wss?:\/\/[^/]+/, BACKEND_WS_BASE)
      }
      const protectedSocket = typeof url === 'string' &&
        (url.includes('/ws/audio') || url.includes('/ws/control') || url.includes('/ws/rehearsal') || url.includes('/api/v1/rehearsal/audio'))
      const requested = protocols
        ? (Array.isArray(protocols) ? protocols : [protocols])
        : []
      if (sessionToken && protectedSocket) {
        requested.push('versepro', `versepro.auth.${sessionToken}`)
      }
      super(url, requested.length ? requested : undefined)
    }
  }
}

await installBackendTransport()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// PWA : service worker actif uniquement en production (en dev il fausserait le HMR)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.warn('Service worker non enregistré :', err)
    })
  })
}
