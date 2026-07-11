import React, { useEffect, useState } from 'react'
import { useStore } from './store.js'
import LiveDetection from './components/LiveDetection.jsx'
import History from './components/History.jsx'
import Statistics from './components/Statistics.jsx'
import LandingPage from './components/LandingPage.jsx'
import Settings from './components/Settings.jsx'
import { ToastHost } from './components/ui.jsx'
import CommandPalette from './components/CommandPalette.jsx'

const NAV_ITEMS = [
  {
    id: 'live',
    label: 'Régie live',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polygon points="10 8 16 12 10 16 10 8" />
      </svg>
    )
  },
  {
    id: 'history',
    label: 'Historique',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 8v4l3 3" />
        <circle cx="12" cy="12" r="10" />
      </svg>
    )
  },
  {
    id: 'statistics',
    label: 'Statistiques',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    )
  },
  {
    id: 'settings',
    label: 'Paramètres',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.04.04a2 2 0 1 1-2.83 2.83l-.04-.04a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.06a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.04.04a2 2 0 1 1-2.83-2.83l.04-.04A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.06A1.7 1.7 0 0 0 4.6 8a1.7 1.7 0 0 0-.34-1.88l-.04-.04a2 2 0 1 1 2.83-2.83l.04.04A1.7 1.7 0 0 0 8.97 3.6 1.7 1.7 0 0 0 10 2.06V2a2 2 0 1 1 4 0v.06a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.04-.04a2 2 0 1 1 2.83 2.83l-.04.04A1.7 1.7 0 0 0 19.4 8c.22.62.82 1.03 1.48 1.03H21a2 2 0 1 1 0 4h-.06A1.7 1.7 0 0 0 19.4 15Z" />
      </svg>
    )
  }
]

function App() {
  // Reprend l'onglet de la dernière session : l'opérateur retrouve sa régie, pas la page d'accueil
  const [activeTab, setActiveTabState] = useState(() => localStorage.getItem('versepro_last_tab') || 'home')
  const setActiveTab = (tab) => {
    localStorage.setItem('versepro_last_tab', tab)
    setActiveTabState(tab)
  }
  const { fetchHistory, fetchStatistics, connectWebSocket, disconnectWebSocket, connected } = useStore()
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    connectWebSocket()
    fetchHistory()
    fetchStatistics()
    return () => { disconnectWebSocket() }
  }, [])

  // ⌘K / Ctrl+K : palette de recherche biblique, disponible partout
  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="app-shell min-h-screen flex font-sans">
      {/* ═══════════ SIDEBAR ═══════════ */}
      {activeTab !== 'home' && (
        <aside className="app-sidebar fixed left-0 top-0 bottom-0 w-[64px] flex flex-col items-center py-6 z-50">
          <button
            onClick={() => setActiveTab('home')}
            className="mb-8 p-2 rounded-xl transition-all duration-200"
            title="Accueil"
          >
            <div className="app-sidebar-logo w-8 h-8 rounded-lg flex items-center justify-center text-xs font-black">
              VP
            </div>
          </button>

          <nav className="flex flex-col gap-3 flex-1">
            {NAV_ITEMS.map((item) => (
              <div key={item.id} className="app-nav-wrap">
                <button
                  onClick={() => setActiveTab(item.id)}
                  className={`app-nav-button w-10 h-10 rounded-xl flex items-center justify-center ${activeTab === item.id ? 'is-active' : ''}`}
                  aria-label={item.label}
                >
                  {item.icon}
                </button>
                <span className="app-nav-tooltip">{item.label}</span>
              </div>
            ))}
          </nav>

          <div className="mt-auto flex flex-col items-center gap-4">
            <div className="app-nav-wrap">
              <div
                className="w-2.5 h-2.5 rounded-full transition-all"
                style={{ background: connected ? 'var(--vp-ok)' : 'var(--vp-live)' }}
              />
              <span className="app-nav-tooltip">{connected ? 'Serveur connecté' : 'Serveur déconnecté'}</span>
            </div>
          </div>
        </aside>
      )}

      {/* ═══════════ CONTENU ═══════════ */}
      <main className={`flex-1 ${activeTab !== 'home' ? 'pl-[64px]' : ''} relative z-10 min-h-screen flex flex-col`}>
        {activeTab === 'home' && <LandingPage setActiveTab={setActiveTab} />}
        {activeTab === 'live' && (
          <div className="p-6 animate-slide-up flex-1">
            <LiveDetection />
          </div>
        )}
        {activeTab === 'history' && (
          <div className="p-6 lg:p-8 animate-slide-up flex-1">
            <History />
          </div>
        )}
        {activeTab === 'statistics' && (
          <div className="p-6 lg:p-8 animate-slide-up flex-1">
            <Statistics />
          </div>
        )}
        {activeTab === 'settings' && (
          <div className="p-6 lg:p-8 animate-slide-up flex-1">
            <Settings />
          </div>
        )}
      </main>

      <ToastHost />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}

export default App
