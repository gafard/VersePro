import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'

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
  const { sendReference } = useStore()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef(null)
  const debounceRef = useRef(null)
  const requestSeq = useRef(0)

  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setActiveIndex(0)
      // Laisse la modale se monter avant de prendre le focus
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const search = useCallback((q) => {
    clearTimeout(debounceRef.current)
    if (!q.trim() || q.trim().length < 2) {
      setResults([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      const seq = ++requestSeq.current
      setSearching(true)
      try {
        const response = await fetch(`/api/v1/bible/search?q=${encodeURIComponent(q.trim())}`)
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
  }, [])

  const project = async (result) => {
    if (!result) return
    onClose()
    await sendReference(result.reference)
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
    <div className="vp-palette-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Recherche biblique">
      <div className="vp-palette" onClick={(e) => e.stopPropagation()}>
        <div className="vp-palette-input-row">
          <Icon name="book" size={16} style={{ color: 'var(--vp-text-faint)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            className="vp-palette-input"
            type="text"
            value={query}
            placeholder="Jn 3:16, « psaume 23 », ou un bout de citation…"
            onChange={(e) => { setQuery(e.target.value); search(e.target.value) }}
            onKeyDown={handleKeyDown}
            aria-label="Rechercher un verset"
          />
          <span className="vp-kbd">Échap</span>
        </div>

        <div className="vp-palette-results" role="listbox">
          {searching && results.length === 0 && (
            <div className="vp-palette-hint">Recherche…</div>
          )}
          {!searching && query.trim().length >= 2 && results.length === 0 && (
            <div className="vp-palette-hint">Aucun verset trouvé. Essayez une référence (Jn 3:16) ou plus de mots de la citation.</div>
          )}
          {query.trim().length < 2 && (
            <div className="vp-palette-hint">
              Tapez une référence ou un extrait du texte — <span className="vp-kbd">↑↓</span> naviguer, <span className="vp-kbd">Entrée</span> projeter.
            </div>
          )}
          {results.map((result, idx) => (
            <button
              key={`${result.reference}-${idx}`}
              className={`vp-palette-row ${idx === activeIndex ? 'is-active' : ''}`}
              onMouseEnter={() => setActiveIndex(idx)}
              onClick={() => project(result)}
              role="option"
              aria-selected={idx === activeIndex}
            >
              <div className="vp-palette-row-head">
                <strong>{result.reference}</strong>
                <span className="vp-palette-method">{METHOD_LABELS[result.detection_method] || result.detection_method}</span>
              </div>
              <p>{result.text || ''}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
