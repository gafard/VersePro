import React, { useEffect, useState } from 'react'
import { isTauri } from '../env.js'
import { useStore } from '../store.js'

/**
 * Garde-fou de fermeture.
 *
 * Fermer la fenêtre pendant un culte coupait la projection sans un mot : l'écran
 * de l'assemblée devenait noir au milieu d'une lecture. Le processus Rust retient
 * désormais la fenêtre quand la régie est en direct, et demande ici confirmation.
 *
 * Hors direct, rien ne change : la fenêtre se ferme immédiatement. On n'ajoute
 * pas une question à un geste anodin — sinon l'opérateur apprend à cliquer
 * « oui » sans lire, et le garde-fou ne protège plus rien.
 */
export default function CloseGuard() {
  const { isListening } = useStore()
  const [demandee, setDemandee] = useState(false)

  // Le processus Rust ne peut pas deviner l'état du direct : on le lui dit.
  useEffect(() => {
    if (!isTauri) return
    window.__TAURI__?.core?.invoke('definir_direct', { actif: Boolean(isListening) })
      .catch(() => { /* commande absente : la fermeture reste libre */ })
  }, [isListening])

  useEffect(() => {
    if (!isTauri) return
    let delier = null
    window.__TAURI__?.event?.listen('versepro://fermeture-demandee', () => setDemandee(true))
      .then((f) => { delier = f })
      .catch(() => { /* sans événement, la fenêtre se ferme normalement */ })
    return () => { if (delier) delier() }
  }, [])

  if (!demandee) return null

  const quitter = () => {
    window.__TAURI__?.core?.invoke('fermer_vraiment').catch(() => setDemandee(false))
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-[2px] z-modal flex items-center justify-center p-4 animate-fade" role="presentation">
      <div className="w-full max-w-[480px] bg-surface-raised border border-border-strong rounded-modal p-6 shadow-elev-4 space-y-4 animate-scale-up" role="alertdialog" aria-modal="true" aria-labelledby="close-guard-titre">
        <div>
          <span className="text-[11px] uppercase tracking-wider font-mono font-semibold text-status-warn">Direct en cours</span>
          <h2 id="close-guard-titre" className="text-lg font-bold text-text-primary mt-0.5">Fermer VersePro maintenant ?</h2>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          Le micro est ouvert et la régie est en service. Fermer l'application
          coupe la projection : l'écran de l'assemblée deviendra noir.
        </p>
        <div className="flex gap-2.5 justify-end pt-2">
          <button
            className="px-4 py-2 text-sm font-medium rounded-input bg-accent text-accent-ink font-semibold hover:bg-accent-hover transition-colors shadow-elev-1"
            autoFocus
            onClick={() => setDemandee(false)}
          >
            Rester en direct
          </button>
          <button
            className="px-4 py-2 text-sm font-medium rounded-input bg-status-danger/15 text-status-danger border border-status-danger/40 hover:bg-status-danger/25 transition-colors"
            onClick={quitter}
          >
            Fermer quand même
          </button>
        </div>
      </div>
    </div>
  )
}
