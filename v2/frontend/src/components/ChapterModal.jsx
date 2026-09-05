import React, { useState, useEffect } from 'react'
import { BACKEND_BASE } from '../env.js'
import { useStore } from '../store.js'

export default function ChapterModal({ reference, onClose }) {
  const sendReference = useStore(s => s.sendReference)
  const activeBible = useStore(s => s.activeBible)
  const availableBibles = useStore(s => s.availableBibles)
  const [loading, setLoading] = useState(true)
  const [chapterData, setChapterData] = useState(null)
  const [error, setError] = useState(null)
  const [selectedVersion, setSelectedVersion] = useState(activeBible || 'LSG')

  // Extraire le livre et chapitre depuis "Jean 3:16" ou "Jean 3"
  const match = /^(.+?)\s+(\d+)(?::(\d+))?/.exec(reference || '')
  const bookName = match ? match[1] : 'Jean'
  const currentChapter = match ? parseInt(match[2], 10) : 1
  const highlightVerse = match && match[3] ? parseInt(match[3], 10) : null

  const [chapterNum, setChapterNum] = useState(currentChapter)

  useEffect(() => {
    let active = true
    const fetchChapter = async () => {
      setLoading(true)
      setError(null)
      try {
        const query = `${bookName} ${chapterNum}`
        const res = await fetch(`${BACKEND_BASE}/api/v1/bible/chapter?q=${encodeURIComponent(query)}&version=${selectedVersion}`)
        if (!res.ok) {
          // Fallback recherche standard
          const searchRes = await fetch(`${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(query)}&limit=50&version=${selectedVersion}`)
          const searchData = await searchRes.json()
          if (active && searchData?.results) {
            setChapterData(searchData.results)
          }
        } else {
          const data = await res.json()
          if (active) setChapterData(data.verses || data.results || [])
        }
      } catch (err) {
        if (active) setError("Impossible de charger les versets du chapitre.")
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchChapter()
    return () => { active = false }
  }, [bookName, chapterNum, selectedVersion])

  const handleProjectVerse = (verseRef) => {
    sendReference(verseRef, selectedVersion)
  }

  return (
    <div className="vp-modal-backdrop z-50 flex items-center justify-center p-4">
      <div className="vp-modal max-w-3xl w-full max-h-[85vh] flex flex-col bg-surface-1 border border-border-weak rounded-2xl shadow-2xl overflow-hidden animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border-weak bg-surface-2">
          <div className="flex items-center gap-3">
            <span className="text-xl">📖</span>
            <div>
              <h2 className="text-lg font-bold text-text-strong">
                {bookName} — Chapitre {chapterNum}
              </h2>
              <p className="text-xs text-text-dim">Parcourez et projetez tous les versets du chapitre</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Version Picker */}
            <select
              value={selectedVersion}
              onChange={(e) => setSelectedVersion(e.target.value)}
              className="vp-input text-xs py-1 px-2 font-mono font-bold text-accent"
            >
              {(availableBibles || ['LSG', 'SEM', 'TOB', 'KJF', 'NBS', 'FC']).map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>

            <button
              onClick={onClose}
              className="vp-btn vp-btn--ghost vp-btn--sm py-1 px-3 text-text-faint hover:text-white"
            >
              ✕ Fermer
            </button>
          </div>
        </div>

        {/* Navigation inter-chapitres */}
        <div className="flex items-center justify-between px-4 py-2 bg-surface-1/50 border-b border-border-weak/50 text-xs">
          <button
            onClick={() => setChapterNum((c) => Math.max(1, c - 1))}
            disabled={chapterNum <= 1}
            className="vp-btn vp-btn--ghost vp-btn--sm py-1 px-3"
          >
            ◄ Chapitre {chapterNum - 1}
          </button>
          <span className="font-mono text-text-dim">Chapitre {chapterNum}</span>
          <button
            onClick={() => setChapterNum((c) => c + 1)}
            className="vp-btn vp-btn--ghost vp-btn--sm py-1 px-3"
          >
            Chapitre {chapterNum + 1} ►
          </button>
        </div>

        {/* Content list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-text-dim text-sm gap-2">
              <span className="animate-spin text-accent">⏳</span> Chargement du chapitre...
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-danger-soft border border-danger text-danger text-xs">
              {error}
            </div>
          ) : !chapterData || chapterData.length === 0 ? (
            <div className="text-center py-12 text-text-faint text-xs">
              Aucun verset trouvé pour ce chapitre.
            </div>
          ) : (
            chapterData.map((v, idx) => {
              const vNum = v.verse || v.verse_start || idx + 1
              const vRef = `${bookName} ${chapterNum}:${vNum}`
              const isTarget = highlightVerse === vNum

              return (
                <div
                  key={vRef}
                  className={`p-3 rounded-xl border transition-all flex items-start gap-3 ${
                    isTarget
                      ? 'bg-emerald-500/10 border-emerald-500/50 shadow-emerald-500/10 shadow-lg'
                      : 'bg-surface-2/60 border-border-weak/60 hover:border-border-weak'
                  }`}
                >
                  <span className={`font-mono text-xs font-bold px-2 py-0.5 rounded ${
                    isTarget ? 'bg-emerald-500 text-white' : 'bg-surface-3 text-accent'
                  }`}>
                    {vNum}
                  </span>
                  <div className="flex-1 text-sm text-text-strong leading-relaxed">
                    {v.text || v.verse_text}
                  </div>
                  <button
                    onClick={() => handleProjectVerse(vRef)}
                    className="vp-btn vp-btn--sm vp-btn--ok flex-shrink-0 text-xs py-1 px-3"
                    title={`Projeter ${vRef}`}
                  >
                    Projeter
                  </button>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
