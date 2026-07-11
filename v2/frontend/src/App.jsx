import React, { useEffect, useState } from 'react'
import { useStore } from './store.js'
import LiveDetection from './components/LiveDetection.jsx'
import History from './components/History.jsx'
import Statistics from './components/Statistics.jsx'
import LandingPage from './components/LandingPage.jsx'
import Settings from './components/Settings.jsx'

function App() {
  const [activeTab, setActiveTab] = useState('home')
  const { fetchHistory, fetchStatistics, connectWebSocket, disconnectWebSocket, connected } = useStore()
  
  useEffect(() => {
    connectWebSocket()
    fetchHistory()
    fetchStatistics()
    return () => { disconnectWebSocket() }
  }, [])
  
  return (
    <div className="min-h-screen flex font-sans app-shell-light">
      {/* ═══════════ SIDEBAR IPAD COPILOT SYSTEM ═══════════ */}
      {activeTab !== 'home' && (
        <aside className="app-sidebar fixed left-0 top-0 bottom-0 w-[64px] flex flex-col items-center py-6 z-50">
          {/* Logo d'application principal */}
          <button 
            onClick={() => setActiveTab('home')} 
            className="mb-8 p-2 rounded-xl hover:bg-white/[0.04] transition-all duration-200"
          >
            <div className="app-sidebar-logo w-8 h-8 rounded-lg flex items-center justify-center text-xs font-black">
              VP
            </div>
          </button>
          
          {/* Icônes d'outils / Navigation */}
          <nav className="flex flex-col gap-4 flex-1">
            <button 
              onClick={() => setActiveTab('live')}
              className={`app-nav-button w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-250 ${
                activeTab === 'live'
                  ? 'is-active'
                  : ''
              }`}
              title="En Direct"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polygon points="10 8 16 12 10 16 10 8"/>
              </svg>
            </button>
            <button 
              onClick={() => setActiveTab('history')}
              className={`app-nav-button w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-250 ${
                activeTab === 'history'
                  ? 'is-active'
                  : ''
              }`}
              title="Historique"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 8v4l3 3"/>
                <circle cx="12" cy="12" r="10"/>
              </svg>
            </button>
            <button 
              onClick={() => setActiveTab('statistics')}
              className={`app-nav-button w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-250 ${
                activeTab === 'statistics'
                  ? 'is-active'
                  : ''
              }`}
              title="Statistiques"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="20" x2="18" y2="10"/>
                <line x1="12" y1="20" x2="12" y2="4"/>
                <line x1="6" y1="20" x2="6" y2="14"/>
              </svg>
            </button>
            <button 
              onClick={() => setActiveTab('settings')}
              className={`app-nav-button w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-250 ${
                activeTab === 'settings'
                  ? 'is-active'
                  : ''
              }`}
              title="Paramètres"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/>
                <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.04.04a2 2 0 1 1-2.83 2.83l-.04-.04a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.06a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.04.04a2 2 0 1 1-2.83-2.83l.04-.04A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.06A1.7 1.7 0 0 0 4.6 8a1.7 1.7 0 0 0-.34-1.88l-.04-.04a2 2 0 1 1 2.83-2.83l.04.04A1.7 1.7 0 0 0 8.97 3.6 1.7 1.7 0 0 0 10 2.06V2a2 2 0 1 1 4 0v.06a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.04-.04a2 2 0 1 1 2.83 2.83l-.04.04A1.7 1.7 0 0 0 19.4 8c.22.62.82 1.03 1.48 1.03H21a2 2 0 1 1 0 4h-.06A1.7 1.7 0 0 0 19.4 15Z"/>
              </svg>
            </button>
          </nav>
          
          {/* Section Profil / Connexion en bas */}
          <div className="mt-auto flex flex-col items-center gap-4">
            {/* Status dot de connexion */}
            <div className="relative group">
              <div className={`w-2 h-2 rounded-full ${connected ? 'bg-blue-600' : 'bg-red-500'} transition-all`} />
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-black text-white text-[9px] font-bold rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap shadow">
                {connected ? 'Serveur Connecté' : 'Serveur Déconnecté'}
              </div>
            </div>
            
            {/* Bouton de profil fictif comme sur la maquette */}
            <div className="app-user-badge w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold">
              U
            </div>
          </div>
        </aside>
      )}
      
      {/* ═══════════ CONTENU PRINCIPAL ═══════════ */}
      <main className={`flex-1 ${activeTab !== 'home' ? 'pl-[64px]' : ''} relative z-10 min-h-screen flex flex-col`}>
        {activeTab === 'home' && <LandingPage setActiveTab={setActiveTab} />}
        {activeTab === 'live' && (
          <div className="p-6 lg:p-8 animate-slide-up flex-1">
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
    </div>
  )
}

export default App
