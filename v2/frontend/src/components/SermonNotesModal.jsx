import React, { useState } from 'react'

export function SermonNotesModal({ isOpen, onClose, onPrepareReference, onProjectReference, addToast }) {
  const [sermonText, setSermonText] = useState('')
  const [loading, setLoading] = useState(false)
  const [extractedVerses, setExtractedVerses] = useState([])

  if (!isOpen) return null

  const handleExtract = async () => {
    if (!sermonText.trim()) return
    setLoading(true)
    try {
      const res = await fetch('/api/v1/bibles/extract_references', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sermonText }),
      })
      const data = await res.json()
      if (data.references && data.references.length > 0) {
        setExtractedVerses(data.references)
        if (addToast) addToast({ message: `✅ ${data.count} verset(s) extrait(s) des notes !`, kind: 'success' })
      } else {
        setExtractedVerses([])
        if (addToast) addToast({ message: '⚠️ Aucun verset biblique explicite n\'a été trouvé.', kind: 'warn' })
      }
    } catch (err) {
      console.error('Erreur extraction notes:', err)
      if (addToast) addToast({ message: '❌ Erreur lors de l\'extraction des versets.', kind: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleAddAll = () => {
    extractedVerses.forEach((item) => {
      if (onPrepareReference) onPrepareReference(item.reference)
    })
    if (addToast) addToast({ message: `📥 ${extractedVerses.length} verset(s) ajoutés au déroulé !`, kind: 'success' })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-surface-1 border border-border-strong rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface-2">
          <div className="flex items-center gap-2">
            <span className="text-xl">📋</span>
            <h3 className="text-lg font-bold text-text">Extraire les Versets d'un Sermon</h3>
          </div>
          <button
            onClick={onClose}
            className="text-text-dim hover:text-text text-xl font-bold p-1 rounded hover:bg-surface-3 transition-all"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6 flex-1 overflow-y-auto space-y-4">
          <p className="text-xs text-text-dim leading-relaxed">
            Collez le texte complet des notes de prédication du pasteur ci-dessous. VersePro va scanner le document et extraire automatiquement toutes les citations bibliques.
          </p>

          <textarea
            value={sermonText}
            onChange={(e) => setSermonText(e.target.value)}
            placeholder="Collez les notes du sermon ici... Ex: Nous allons lire dans Jérémie 17:7 puis Hébreux 11:1..."
            className="w-full h-36 p-3 bg-surface-2 border border-border rounded-lg text-sm text-text placeholder:text-text-faint focus:outline-none focus:border-accent font-sans resize-y"
          />

          <div className="flex justify-end">
            <button
              onClick={handleExtract}
              disabled={loading || !sermonText.trim()}
              className="vp-btn vp-btn--primary px-5 py-2 text-xs font-semibold flex items-center gap-2"
            >
              {loading ? (
                <span>⚡ Analyse en cours…</span>
              ) : (
                <>
                  <span>⚡</span>
                  <span>Extraire les versets</span>
                </>
              )}
            </button>
          </div>

          {/* Results List */}
          {extractedVerses.length > 0 && (
            <div className="mt-6 pt-4 border-t border-border space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text uppercase tracking-wider">
                  Versets Détectés ({extractedVerses.length})
                </h4>
                <button
                  onClick={handleAddAll}
                  className="vp-btn vp-btn--secondary px-3 py-1 text-xs font-semibold"
                >
                  📥 Tout ajouter au déroulé
                </button>
              </div>

              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {extractedVerses.map((v, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-surface-2 border border-border rounded-lg flex items-start justify-between gap-3 hover:border-accent/50 transition-all"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-sm text-accent mb-0.5">{v.reference}</div>
                      <p className="text-xs text-text-dim line-clamp-2">{v.text}</p>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => {
                          if (onPrepareReference) onPrepareReference(v.reference)
                        }}
                        className="px-2.5 py-1 rounded text-xs bg-surface-3 hover:bg-surface-1 text-text-dim hover:text-white font-medium transition-all"
                        title="Préparer sans projeter"
                      >
                        Préparer
                      </button>
                      {onProjectReference && (
                        <button
                          onClick={() => {
                            onProjectReference(v.reference)
                            onClose()
                          }}
                          className="px-2.5 py-1 rounded text-xs bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-300 font-semibold border border-emerald-500/30 transition-all"
                          title="Projeter immédiatement"
                        >
                          Projeter
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
