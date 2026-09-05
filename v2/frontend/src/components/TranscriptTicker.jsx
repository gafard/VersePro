import React, { useLayoutEffect, useRef } from 'react'

/**
 * Ticker de transcription — défilement doux garanti.
 *
 * Deux principes non négociables :
 * 1. `contain: inline-size` (CSS) : le texte, aussi long soit-il, ne peut
 *    JAMAIS élargir la page — le conteneur est hermétique vers l'extérieur.
 * 2. La glisse se fait par UNE écriture de transform par mise à jour,
 *    interpolée par une transition CSS (compositeur GPU) : aucun saut de
 *    layout, aucun re-montage de spans, aucune saccade.
 */
export default function TranscriptTicker({ text, placeholder }) {
  const flowRef = useRef(null)
  const innerRef = useRef(null)

  const words = (text || '').trim().split(/\s+/).filter(Boolean).slice(-60)
  const oldPart = words.slice(0, -6).join(' ')
  const recentPart = words.slice(-6).join(' ')

  // Après chaque rendu du texte : cale la fin du flux sur le bord droit.
  // La transition CSS transforme ce déplacement en glisse fluide.
  useLayoutEffect(() => {
    const flow = flowRef.current
    const inner = innerRef.current
    if (!flow || !inner) return
    const target = Math.min(0, flow.clientWidth - inner.scrollWidth)
    inner.style.transform = `translateX(${target}px)`
  }, [text])

  return (
    <div className="vp-ticker-flow" ref={flowRef}>
      {/* transform initial explicite : la toute première glisse s'anime aussi
          (une transition CSS ne s'interpole pas depuis transform:none) */}
      <div className="vp-ticker-inner" ref={innerRef} style={{ transform: 'translateX(0px)' }}>
        {words.length > 0 ? (
          <>
            <span className="seg-old">{oldPart}</span>
            {oldPart ? ' ' : ''}
            <span className="seg-recent">{recentPart}</span>
          </>
        ) : (
          <span className="vp-ticker-placeholder">{placeholder}</span>
        )}
      </div>
    </div>
  )
}
