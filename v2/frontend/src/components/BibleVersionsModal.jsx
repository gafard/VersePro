import React, { useState } from 'react'
import { useStore } from '../store.js'

const BIBLE_CATALOG = [
  { code: 'LSG', name: 'Louis Segond 1910', lang: '🇫🇷 Français', status: 'installed', desc: 'Version classique de référence en langue française.' },
  { code: 'SEM', 'name': 'La Bible du Semeur', lang: '🇫🇷 Français', status: 'installed', desc: 'Traduction dynamique moderne et accessible.' },
  { code: 'TOB', name: 'Traduction Œcuménique (TOB)', lang: '🇫🇷 Français', status: 'available', desc: 'Version œcuménique révisée avec notes canoniques.' },
  { code: 'KJF', name: 'King James Française', lang: '🇫🇷 Français', status: 'installed', desc: 'Fidèle à la tradition de la King James.' },
  { code: 'NBS', name: 'Nouvelle Bible Segond', lang: '🇫🇷 Français', status: 'available', desc: 'Traduction littérale d\'étude rigoureuse.' },
  { code: 'FC', name: 'Français Courant', lang: '🇫🇷 Français', status: 'available', desc: 'Français contemporain fluide et accessible.' },
  { code: 'KJV', name: 'King James Version 1611', lang: '🇬🇧 English', status: 'available', desc: 'Classic English Authorized Version.' },
  { code: 'ASV', name: 'American Standard Version (1901)', lang: '🇺🇸 English', status: 'available', desc: 'Historical American Standard English translation.' },
  { code: 'NVI', name: 'Nueva Versión Internacional', lang: '🇪🇸 Español', status: 'available', desc: 'Traducción moderna en español contemporáneo.' }
]

export default function BibleVersionsModal({ onClose }) {
  const { availableBibles, activeBible, selectBible, fetchBibles } = useStore()
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState('official') // 'official' | 'custom'
  const [filterLang, setFilterLang] = useState('all')
  const [loadingCode, setLoadingCode] = useState(null)

  const handleSelect = async (code) => {
    setLoadingCode(code)
    try {
      await selectBible(code)
      await fetchBibles()
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
    <div className="vp-modal-backdrop z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="vp-modal max-w-2xl w-full max-h-[85vh] flex flex-col bg-surface-1 border border-border-weak rounded-2xl shadow-2xl overflow-hidden animate-scale-in" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border-weak bg-surface-2">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📚</span>
            <div>
              <h2 className="text-lg font-bold text-text-strong">Gestionnaire de Bibles</h2>
              <p className="text-xs text-text-dim">Gérez vos versions officielles et traductions actives</p>
            </div>
          </div>
          <button onClick={onClose} className="vp-btn vp-btn--ghost vp-btn--sm">✕</button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border-weak bg-surface-1 px-4 gap-4 pt-2">
          <button
            className={`py-2 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'official'
                ? 'border-accent text-accent'
                : 'border-transparent text-text-dim hover:text-text-strong'
            }`}
            onClick={() => setActiveTab('official')}
          >
            Versions Officielles
          </button>
        </div>

        {/* Filters & Search */}
        <div className="p-4 border-b border-border-weak/60 flex items-center gap-3 bg-surface-1/40">
          <div className="relative flex-1">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher par nom, abréviation (LSG, SEM, KJV)..."
              className="vp-input w-full py-1.5 px-3 text-xs pl-8"
            />
            <span className="absolute left-2.5 top-2 text-text-faint text-xs">🔍</span>
          </div>

          <select
            value={filterLang}
            onChange={(e) => setFilterLang(e.target.value)}
            className="vp-input text-xs py-1.5 px-2 font-mono text-text-dim"
          >
            <option value="all">Toutes les langues</option>
            <option value="fr">🇫🇷 Français</option>
            <option value="en">🇬🇧 English</option>
          </select>
        </div>

        {/* Bible List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {filteredBibles.map((bible) => {
            const isInstalled = availableBibles.includes(bible.code)
            const isActive = activeBible === bible.code
            const isLoading = loadingCode === bible.code

            return (
              <div
                key={bible.code}
                className={`p-3.5 rounded-xl border flex items-center justify-between gap-4 transition-all ${
                  isActive
                    ? 'bg-accent/10 border-accent/40 shadow-sm'
                    : 'bg-surface-2/70 border-border-weak/70 hover:border-border-weak'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-bold px-2 py-1 rounded bg-surface-3 text-accent border border-accent/20">
                    {bible.code}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-text-strong">{bible.name}</h4>
                      <span className="text-[10px] text-text-faint">{bible.lang}</span>
                    </div>
                    <p className="text-xs text-text-dim mt-0.5">{bible.desc}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => handleSelect(bible.code)}
                    disabled={isLoading || isActive}
                    className={`vp-btn vp-btn--sm text-xs py-1 px-3 ${
                      isActive
                        ? 'vp-btn--ok font-bold shadow-emerald-500/20'
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
      </div>
    </div>
  )
}
