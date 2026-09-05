import React, { useState, useCallback } from 'react'
import { useStore } from '../store.js'

/**
 * Bouton micro isolé dans son propre composant pour contenir les re-rendus
 * haute fréquence (volume VU-mètre ~23 fps) sans affecter le reste de l'app.
 *
 * Avant cette extraction, `volume` était lu dans App.jsx — chaque frame audio
 * provoquait un re-rendu de la racine et de tous ses enfants.
 */
export default function MicButton() {
  const isListening = useStore(s => s.isListening)
  const toggleListening = useStore(s => s.toggleListening)
  const volume = useStore(s => s.volume)

  return (
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
  )
}
