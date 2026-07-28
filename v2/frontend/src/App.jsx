import React, { useCallback, useEffect, useState } from 'react'
import { useStore } from './store.js'
import LiveDetection from './components/LiveDetection.jsx'
import History from './components/History.jsx'
import Statistics from './components/Statistics.jsx'
import LandingPage from './components/LandingPage.jsx'
import Settings from './components/Settings.jsx'
import { ToastHost } from './components/ui.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import FirstRunWizard from './components/FirstRunWizard.jsx'
import LaunchIntro from './components/LaunchIntro.jsx'
import CloseGuard from './components/CloseGuard.jsx'

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
  const [showLaunchIntro, setShowLaunchIntro] = useState(() => {
    try { return sessionStorage.getItem('versepro_launch_intro_seen') !== 'true' } catch { return true }
  })
  const closeLaunchIntro = useCallback(() => {
    try { sessionStorage.setItem('versepro_launch_intro_seen', 'true') } catch { /* stockage privé */ }
    setShowLaunchIntro(false)
  }, [])

  // Reprend l'onglet de la dernière session : l'opérateur retrouve sa régie, pas la page d'accueil
  const [activeTab, setActiveTabState] = useState(() => localStorage.getItem('versepro_last_tab') || 'home')
  const setActiveTab = (tab) => {
    localStorage.setItem('versepro_last_tab', tab)
    setActiveTabState(tab)
  }
  
  const { 
    fetchHistory, 
    fetchStatistics, 
    checkBackendHealth,
    fetchBibles,
    fetchSettings,
    fetchProjectionState,
    hydrateQueueFromSession,
    fetchIntelligenceStatus,
    disconnectWebSocket, 
    connected,
    connectionStatus,
    asrMode,
    aiActive,
    propresenterConnected,
    isListening,
    toggleListening,
    volume,
    onAir
  } = useStore()

  const serverStatus = connected
    ? { label: 'Serveur', tooltip: 'Serveur connecté', tone: 'is-ok', color: 'var(--success)' }
    : connectionStatus === 'starting'
      ? { label: 'Démarrage', tooltip: 'Initialisation du serveur', tone: 'is-warn', color: 'var(--warning)' }
      : connectionStatus === 'reconnecting'
        ? { label: 'Reconnexion', tooltip: 'Reconnexion au serveur', tone: 'is-warn', color: 'var(--warning)' }
        : { label: 'Hors ligne', tooltip: 'Serveur déconnecté', tone: 'is-bad', color: 'var(--danger)' }
  
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [firstRun, setFirstRun] = useState(() => {
    try { return localStorage.getItem('versepro_first_run_done') !== 'true' } catch { return false }
  })
  const [clock, setClock] = useState(() => new Date())

  useEffect(() => {
    let bootstrapped = false
    const bootstrap = async () => {
      const healthy = await checkBackendHealth()
      if (healthy && !bootstrapped) {
        bootstrapped = true
        await Promise.all([
          fetchHistory(),
          fetchStatistics(),
          fetchBibles(),
          fetchSettings(),
          fetchProjectionState(),
          hydrateQueueFromSession(),
          fetchIntelligenceStatus()
        ])
      }
    }
    bootstrap()
    const timer = setInterval(bootstrap, 5000)
    return () => {
      clearInterval(timer)
      disconnectWebSocket()
    }
  }, [])

  // Horloge de régie globale
  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(timer)
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

  // Libellé de l'onglet actif
  const getTabLabel = () => {
    switch (activeTab) {
      case 'live': return 'Régie en direct'
      case 'history': return 'Historique & Rapports'
      case 'statistics': return 'Statistiques d\'activité'
      case 'settings': return 'Paramètres'
      default: return 'VersePro'
    }
  }

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
            <div className="app-sidebar-logo w-8 h-8 rounded-lg flex items-center justify-center overflow-hidden">
              <img src="/icons/icon-192.png" alt="VersePro" className="w-full h-full object-contain" />
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
                style={{ background: serverStatus.color }}
              />
              <span className="app-nav-tooltip">{serverStatus.tooltip}</span>
            </div>
          </div>
        </aside>
      )}

      {/* ═══════════ CONTENU ═══════════ */}
      <main className={`flex-1 ${activeTab !== 'home' ? 'pl-[64px]' : ''} relative z-10 min-h-screen flex flex-col`}>
        {activeTab !== 'home' && (
          <header className="global-header">
            <div className="global-header-left">
              <h1>{getTabLabel()}</h1>
              {onAir && (
                <div className="global-program-preview" title={onAir.text}>
                  <span className="dot" />
                  <span className="label">Direct :</span>
                  <span className="ref">{onAir.reference}</span>
                </div>
              )}
            </div>

            <div className="global-header-right">
              <span className={`vp-chip ${serverStatus.tone}`}>
                <span className="dot" />{serverStatus.label}
              </span>
              <span className={`vp-chip ${['vosk', 'whisper'].includes(asrMode) ? 'is-warn' : 'is-accent'}`}>
                <span className="dot" />{asrMode === 'vosk' ? 'Vosk sélectionné' : asrMode === 'whisper' ? 'Whisper sélectionné' : 'Deepgram sélectionné'}
              </span>
              <span className={`vp-chip ${aiActive ? 'is-accent' : ''}`}>
                <span className="dot" />IA {aiActive ? 'prête' : 'off'}
              </span>
              <span className={`vp-chip ${propresenterConnected ? 'is-ok' : 'is-warn'}`}>
                <span className="dot" />{propresenterConnected ? 'ProPresenter' : 'PP manuel'}
              </span>

              <span className="global-clock">
                {clock.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>

              <button 
                className={`global-mic-btn ${isListening ? 'is-live' : ''}`} 
                onClick={toggleListening}
                title={isListening ? 'Micro activé — cliquer pour désactiver' : 'Démarrer le micro'}
              >
                <span className="mic-dot" />
                {isListening ? 'LIVE' : 'Micro'}
                <span className="mic-vu">
                  <div style={{ width: `${isListening ? volume : 0}%` }} />
                </span>
              </button>
            </div>
          </header>
        )}

        {activeTab === 'home' && <LandingPage setActiveTab={setActiveTab} />}
        {activeTab === 'live' && (
          <div className="p-6 animate-slide-up flex-1">
            <LiveDetection setActiveTab={setActiveTab} />
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
      {firstRun && <FirstRunWizard onDone={() => { setFirstRun(false); setActiveTab('live') }} />}
      {showLaunchIntro && <LaunchIntro onDone={closeLaunchIntro} />}
      <CloseGuard />
    </div>
  )
}

export default App
