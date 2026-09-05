import React, { useEffect } from 'react'
import { isTauri } from '../env.js'
import { useStore } from '../store.js'

const formatBytes = (value) => {
  if (!value) return ''
  const units = ['o', 'Ko', 'Mo', 'Go']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`
}

export default function UpdateManager({ enabled = true }) {
  const info = useStore(s => s.desktopUpdateInfo)
  const status = useStore(s => s.desktopUpdateStatus)
  const error = useStore(s => s.desktopUpdateError)
  const progress = useStore(s => s.desktopUpdateProgress)
  const dialogOpen = useStore(s => s.desktopUpdateDialogOpen)
  const isListening = useStore(s => s.isListening)
  const onAir = useStore(s => s.onAir)
  const checkUpdate = useStore(s => s.checkDesktopUpdate)
  const installUpdate = useStore(s => s.installDesktopUpdate)
  const dismissUpdate = useStore(s => s.dismissDesktopUpdate)
  const setProgress = useStore(s => s.setDesktopUpdateProgress)

  useEffect(() => {
    if (!isTauri || !enabled) return undefined
    // Laisse le backend et l'onboarding démarrer avant le contrôle réseau.
    const timer = window.setTimeout(() => checkUpdate({ silent: true }), 8000)
    return () => window.clearTimeout(timer)
  }, [checkUpdate, enabled])

  useEffect(() => {
    if (!isTauri) return undefined
    let unlisten = null
    window.__TAURI__?.event?.listen('versepro://mise-a-jour-progression', (event) => {
      setProgress(event.payload || {})
    }).then((stop) => { unlisten = stop }).catch(() => {})
    return () => { if (unlisten) unlisten() }
  }, [setProgress])

  if (!dialogOpen || !info.update_available) return null

  const busy = status === 'downloading' || status === 'installing'
  const liveBlocked = Boolean(isListening || onAir)
  const progressLabel = status === 'installing'
    ? 'Installation et vérification…'
    : progress.total
      ? `${formatBytes(progress.downloaded)} / ${formatBytes(progress.total)}`
      : 'Téléchargement sécurisé…'

  return (
    <div className="vp-modal-backdrop" role="presentation">
      <div className="vp-modal update-modal" role="alertdialog" aria-modal="true" aria-labelledby="update-title">
        <span className="update-kicker">MISE À JOUR SIGNÉE</span>
        <h2 id="update-title">VersePro {info.latest} est disponible</h2>
        <p className="vp-modal-intro">
          Version installée : {info.current}. La mise à jour sera vérifiée avant installation,
          puis VersePro redémarrera automatiquement.
        </p>

        {info.notes && <div className="update-notes">{info.notes}</div>}

        {busy && (
          <div className="update-progress" role="status" aria-live="polite">
            <div className="update-progress-track">
              <span style={{ width: `${progress.percent || (status === 'installing' ? 100 : 8)}%` }} />
            </div>
            <span>{progressLabel}</span>
          </div>
        )}

        {liveBlocked && !busy && (
          <div className="update-live-warning">
            Mise à jour protégée : arrêtez le micro et videz le verset à l’antenne.
          </div>
        )}
        {error && <div className="update-error">{error}</div>}

        <div className="update-actions">
          <button type="button" className="vp-btn vp-btn--ghost" onClick={dismissUpdate} disabled={busy}>
            Plus tard
          </button>
          <button type="button" className="vp-btn vp-btn--primary" onClick={installUpdate} disabled={busy || liveBlocked}>
            {busy ? progressLabel : 'Télécharger et installer'}
          </button>
        </div>
      </div>
    </div>
  )
}
