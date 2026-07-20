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
if (isTauri) {
  const origFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    if (typeof input === 'string' && input.startsWith('/')) input = BACKEND_BASE + input
    return origFetch(input, init)
  }
  const OrigWebSocket = window.WebSocket
  window.WebSocket = class extends OrigWebSocket {
    constructor(url, protocols) {
      if (typeof url === 'string') {
        if (url.startsWith('/')) url = BACKEND_WS_BASE + url
        else url = url.replace(/^wss?:\/\/[^/]+/, BACKEND_WS_BASE)
      }
      super(url, protocols)
    }
  }
}

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
