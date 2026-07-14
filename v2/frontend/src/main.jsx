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


// Sous Tauri, le frontend est servi en tauri://localhost : les appels relatifs
// (/api, /ws) sont réécrits vers le backend local — zéro changement ailleurs.
if (window.__TAURI__) {
  const HTTP_BASE = 'http://127.0.0.1:8001'
  const WS_BASE = 'ws://127.0.0.1:8001'
  const origFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    if (typeof input === 'string' && input.startsWith('/')) input = HTTP_BASE + input
    return origFetch(input, init)
  }
  const OrigWebSocket = window.WebSocket
  window.WebSocket = class extends OrigWebSocket {
    constructor(url, protocols) {
      if (typeof url === 'string') {
        if (url.startsWith('/')) url = WS_BASE + url
        else url = url.replace(/^wss?:\/\/[^/]+/, WS_BASE)
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
