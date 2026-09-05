import React, { useState } from 'react'
import { useStore } from '../store.js'
import BibleImport from './BibleImport.jsx'

const BIBLE_CATALOG = [
  { code: 'LSG', name: 'Louis Segond 1910', lang: '🇫🇷 Français', tag: 'Officielle', desc: 'Version classique de référence en langue française.' },
  { code: 'SEM', name: 'La Bible du Semeur', lang: '🇫🇷 Français', tag: 'Sous Droits', desc: 'Traduction dynamique moderne et accessible.' },
  { code: 'TOB', name: 'Traduction Œcuménique (TOB)', lang: '🇫🇷 Français', tag: 'Officielle', desc: 'Version œcuménique révisée avec notes canoniques.' },
  { code: 'KJF', name: 'King James Française', lang: '🇫🇷 Français', tag: 'Officielle', desc: 'Fidèle à la tradition de la King James.' },
  { code: 'NBS', name: 'Nouvelle Bible Segond', lang: '🇫🇷 Français', tag: 'Officielle', desc: 'Traduction littérale d\'étude rigoureuse.' },
  { code: 'FC', name: 'Français Courant', lang: '🇫🇷 Français', tag: 'Officielle', desc: 'Français contemporain fluide et accessible.' },
  { code: 'KJV', name: 'King James Version 1611', lang: '🇬🇧 English', tag: 'English', desc: 'Classic English Authorized Version.' },
  { code: 'ASV', name: 'American Standard Version', lang: '🇺🇸 English', tag: 'English', desc: 'Historical American Standard English translation.' },
  { code: 'NVI', name: 'Nueva Versión Internacional', lang: '🇪🇸 Español', tag: 'Español', desc: 'Traducción moderna en español contemporáneo.' }
]

export default function BibleVersionsModal({ onClose }) {
  const availableBibles = useStore(s => s.availableBibles)
  const activeBible = useStore(s => s.activeBible)
  const selectBible = useStore(s => s.selectBible)
  const fetchBibles = useStore(s => s.fetchBibles)
  const addToast = useStore(s => s.addToast)
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState('official') // 'official' | 'custom'
  const [filterLang, setFilterLang] = useState('all')
  const [loadingCode, setLoadingCode] = useState(null)

  const handleSelect = async (code) => {
    if (loadingCode || activeBible === code) return
    setLoadingCode(code)
    try {
      await selectBible(code)
      await fetchBibles()
      addToast({ message: `Version active : ${code}`, kind: 'success' })
    } catch (err) {
      addToast({ message: `Erreur sélection Bible : ${err.message}`, kind: 'error' })
    } finally {
      setLoadingCode(null)
    }
  }

  const filteredBibles = BIBLE_CATALOG.filter((b) => {
    const matchesSearch = b.name.toLowerCase().includes(search.toLowerCase()) || b.code.toLowerCase().includes(search.toLowerCase())
    const matchesLang = filterLang === 'all' || (filterLang === 'fr' && b.lang.includes('Français')) || (filterLang === 'en' && b.lang.includes('English'))
    return matchesSearch && matchesLang
  })

  return (
    <div className="vp-modal-backdrop z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in" onClick={onClose}>
      <div 
        className="vp-modal max-w-3xl w-full max-h-[85vh] flex flex-col bg-surface-1/95 border border-white/10 rounded-2xl shadow-2xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 px-6 border-b border-white/10 bg-surface-2/80 backdrop-blur">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent text-xl shadow-inner">
              <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-text-strong tracking-wide">Gestionnaire de Bibles</h2>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-accent/20 text-accent font-semibold border border-accent/30">
                  {activeBible || 'LSG'} actif
                </span>
              </div>
              <p className="text-xs text-text-dim mt-0.5">Sélectionnez la version de référence pour la détection et la projection</p>
            </div>
          </div>
          <button 
            onClick={onClose} 
            className="w-8 h-8 rounded-lg flex items-center justify-center text-text-dim hover:text-text-strong hover:bg-white/10 transition-all"
            title="Fermer"
          >
            ✕
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-white/10 bg-surface-1 px-6 gap-6 pt-3">
          <button
            className={`pb-2.5 px-1 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'official'
                ? 'border-accent text-accent'
                : 'border-transparent text-text-dim hover:text-text-strong'
            }`}
            onClick={() => setActiveTab('official')}
          >
            <span>📖 Versions Officielles</span>
            <span className="text-[10px] font-mono bg-surface-3 px-1.5 py-0.5 rounded text-text-dim">{filteredBibles.length}</span>
          </button>

          <button
            className={`pb-2.5 px-1 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'custom'
                ? 'border-accent text-accent'
                : 'border-transparent text-text-dim hover:text-text-strong'
            }`}
            onClick={() => setActiveTab('custom')}
          >
            <span>📁 Importer une Bible (XML/JSON)</span>
          </button>
        </div>

        {/* Tab 1: Versions Officielles */}
        {activeTab === 'official' && (
          <>
            {/* Filters & Search */}
            <div className="p-4 px-6 border-b border-white/5 flex items-center gap-3 bg-surface-1/40">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Rechercher par nom ou abréviation (LSG, SEM, KJV)..."
                  className="vp-input w-full py-1.5 px-3 text-xs pl-8 bg-surface-2/80 border-white/10 focus:border-accent"
                />
                <span className="absolute left-2.5 top-2 text-text-faint text-xs">🔍</span>
              </div>

              <select
                value={filterLang}
                onChange={(e) => setFilterLang(e.target.value)}
                className="vp-input text-xs py-1.5 px-3 font-mono text-text-dim bg-surface-2/80 border-white/10 rounded-lg cursor-pointer"
              >
                <option value="all">Toutes les langues</option>
                <option value="fr">🇫🇷 Français</option>
                <option value="en">🇬🇧 English</option>
              </select>
            </div>

            {/* Bible Cards List */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {filteredBibles.map((bible) => {
                const isInstalled = availableBibles.includes(bible.code)
                const isActive = activeBible === bible.code
                const isLoading = loadingCode === bible.code

                return (
                  <div
                    key={bible.code}
                    onClick={() => handleSelect(bible.code)}
                    className={`p-4 rounded-xl border flex items-center justify-between gap-4 transition-all cursor-pointer ${
                      isActive
                        ? 'bg-accent/15 border-accent/50 shadow-lg shadow-accent/5 ring-1 ring-accent/30'
                        : isInstalled
                        ? 'bg-surface-2/80 border-white/10 hover:border-accent/40 hover:bg-surface-2'
                        : 'bg-surface-2/40 border-white/5 opacity-80 hover:opacity-100 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center gap-3.5">
                      <span className={`font-mono text-xs font-bold px-2.5 py-1 rounded-lg border transition-all ${
                        isActive
                          ? 'bg-accent text-surface-1 border-accent shadow-sm'
                          : 'bg-surface-3 text-accent border-accent/20'
                      }`}>
                        {bible.code}
                      </span>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-text-strong">{bible.name}</h4>
                          <span className="text-[10px] text-text-dim bg-surface-3 px-2 py-0.5 rounded border border-white/5">
                            {bible.lang}
                          </span>
                        </div>
                        <p className="text-xs text-text-dim mt-1">{bible.desc}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleSelect(bible.code)
                        }}
                        disabled={isLoading || isActive}
                        className={`vp-btn vp-btn--sm text-xs py-1.5 px-3.5 transition-all ${
                          isActive
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold'
                            : isInstalled
                            ? 'vp-btn--primary'
                            : 'vp-btn--ghost'
                        }`}
                      >
                        {isLoading ? 'Chargement…' : isActive ? '✓ Version Active' : isInstalled ? 'Utiliser' : 'Activer'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {/* Tab 2: Importer une Bible */}
        {activeTab === 'custom' && (
          <div className="flex-1 overflow-y-auto p-6">
            <BibleImport />
          </div>
        )}
      </div>
    </div>
  )
}
