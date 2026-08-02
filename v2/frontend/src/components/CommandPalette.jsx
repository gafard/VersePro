import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'
import { BACKEND_BASE } from '../env.js'

const METHOD_LABELS = {
  explicit: 'Référence',
  chapter_candidate: 'Chapitre',
  adjacent: 'Verset suivant',
  text_phrase: 'Citation connue',
  text_index: 'Texte exact',
  text_substring: 'Texte exact',
  text_fuzzy: 'Citation approchée',
}

/**
 * Palette de commande (⌘K / Ctrl+K) : recherche unifiée dans la Bible —
 * référence explicite, début de texte ou citation approximative — avec
 * aperçu du verset et projection immédiate à Entrée.
 */
export default function CommandPalette({ open, onClose }) {
  const { sendReference, onAir, activeBible } = useStore()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef(null)
  const debounceRef = useRef(null)
  const requestSeq = useRef(0)

  const BIBLE_VERSIONS = {
    sem: { code: 'SEM', name: 'La Bible du Semeur' },
    semeur: { code: 'SEM', name: 'La Bible du Semeur' },
    lsg: { code: 'LSG', name: 'Louis Segond 1910' },
    segond: { code: 'LSG', name: 'Louis Segond 1910' },
    tob: { code: 'TOB', name: 'Traduction Œcuménique (TOB)' },
    nbs: { code: 'NBS', name: 'Nouvelle Bible Segond' },
    kjf: { code: 'KJF', name: 'King James Française' },
    fc: { code: 'FC', name: 'Français Courant' },
    bfc: { code: 'FC', name: 'Français Courant' }
  }

  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setActiveIndex(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const search = useCallback((q) => {
    clearTimeout(debounceRef.current)
    const trimmed = q.trim().toLowerCase()
    if (!trimmed) {
      setResults([])
      return
    }

    // Détection immédiate des mots-clés de version
    if (BIBLE_VERSIONS[trimmed] && onAir?.reference) {
      const verObj = BIBLE_VERSIONS[trimmed]
      setResults([{
        isVersionCommand: true,
        versionCode: verObj.code,
        versionName: verObj.name,
        reference: onAir.reference,
        text: `Basculer ${onAir.reference} vers la version ${verObj.name} (${verObj.code})`
      }])
      setActiveIndex(0)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const seq = ++requestSeq.current
      setSearching(true)
      try {
        const response = await fetch(`${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(trimmed)}`)
        const data = await response.json()
        if (seq === requestSeq.current) {
          setResults(data.results || [])
          setActiveIndex(0)
        }
      } catch {
        if (seq === requestSeq.current) setResults([])
      } finally {
        if (seq === requestSeq.current) setSearching(false)
      }
    }, 180)
  }, [onAir])

  const project = async (result) => {
    if (!result) return
    onClose()
    if (result.isVersionCommand) {
      await sendReference(result.reference, result.versionCode)
    } else {
      await sendReference(result.reference)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(results.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      project(results[activeIndex])
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-[2px] z-palette flex justify-center items-start pt-[12vh] px-5 pb-5 animate-fade"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Recherche biblique"
    >
      <div
        className="w-full max-w-[620px] bg-surface-raised border border-border-strong rounded-card shadow-elev-4 overflow-hidden animate-slide-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-border">
          <Icon name="book" size={16} className="text-text-faint shrink-0" />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent border-0 outline-none text-text-primary text-[15px] placeholder:text-text-faint"
            type="text"
            value={query}
            placeholder="Jn 3:16, « psaume 23 », ou un bout de citation…"
            onChange={(e) => { setQuery(e.target.value); search(e.target.value) }}
            onKeyDown={handleKeyDown}
            aria-label="Rechercher un verset"
          />
          <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-surface-elevated border border-border text-text-faint">Échap</span>
        </div>

        <div className="max-h-[46vh] overflow-y-auto p-1.5" role="listbox">
          {searching && results.length === 0 && (
            <div className="p-4 text-[12.5px] text-text-faint leading-relaxed">Recherche…</div>
          )}
          {!searching && query.trim().length >= 2 && results.length === 0 && (
            <div className="p-4 text-[12.5px] text-text-faint leading-relaxed">
              Aucun verset trouvé. Essayez une référence (Jn 3:16) ou plus de mots de la citation.
            </div>
          )}
          {query.trim().length < 2 && (
            <div className="p-4 text-[12.5px] text-text-faint leading-relaxed">
              Tapez une référence ou un extrait du texte — <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-surface-elevated border border-border text-text-faint">↑↓</span> naviguer, <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-surface-elevated border border-border text-text-faint">Entrée</span> projeter.
            </div>
          )}
          {results.map((result, idx) => {
            const isActive = idx === activeIndex
            return (
              <button
                key={`${result.reference}-${idx}`}
                className={`block w-full text-left bg-transparent border-0 rounded-input p-2.5 cursor-pointer transition-colors duration-150 ${
                  isActive ? 'bg-surface-hover' : 'hover:bg-surface-elevated'
                }`}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => project(result)}
                role="option"
                aria-selected={isActive}
              >
                <div className="flex items-center justify-between gap-2.5">
                  <strong className="text-[13.5px] text-text-primary font-semibold">{result.reference}</strong>
                  <span className={`text-[10.5px] font-mono font-semibold uppercase tracking-wider transition-colors ${
                    isActive ? 'text-accent' : 'text-text-faint'
                  }`}>
                    {METHOD_LABELS[result.detection_method] || result.detection_method}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-snug text-text-secondary line-clamp-2">{result.text || ''}</p>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
