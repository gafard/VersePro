import React, { useMemo } from 'react'
import { useStore } from '../store.js'

/*
 * Landing — Hallmark · Lumen (Night Foundry) · Marquee Hero
 * Registre deux-casses : prose en bas-de-casse, labels mono en MAJUSCULES.
 * La landing montre le logiciel lui-même : pas d'illustration IA, pas de chrome OS factice.
 * Les valeurs affichées doivent être vérifiables dans l'application.
 */

// Enveloppe procédurale de la bande-mètre : sinus + harmonique, jamais uniforme
const METER_BARS = Array.from({ length: 64 }, (_, i) => {
  const t = i / 63
  const envelope = Math.sin(t * Math.PI)
  const detail = 0.55 + 0.45 * Math.sin(i * 1.7) * Math.sin(i * 0.35)
  return Math.round(4 + envelope * detail * 24)
})

export default function LandingPage({ setActiveTab }) {
  const {
    history,
    connected,
    propresenterConnected,
    availableBibles,
    semanticStatus,
    asrStatus,
    currentTranscript,
    projectionQueue,
    onAir,
    isListening,
    waveform
  } = useStore()
  const recentVerses = useMemo(() => history.slice(0, 3), [history])
  const pending = useMemo(
    () => projectionQueue.filter((item) => item.status === 'pending').slice(0, 2),
    [projectionQueue]
  )
  const previewPrimary = pending[0] || onAir || recentVerses[0]
  const previewSecondary = pending[1]

  return (
    <div className="lp">
      {/* ── Nav · N9 edge-aligned minimal ── */}
      <nav className="lp-nav" aria-label="Navigation principale">
        <button className="lp-wordmark flex items-center gap-2" onClick={() => setActiveTab('home')}>
          <img src="/icons/icon-192.png" alt="" aria-hidden="true" className="w-5 h-5 rounded object-contain" />
          <span>versepro</span>
        </button>
        <div className="lp-nav-right">
          <button className="lp-nav-link" onClick={() => setActiveTab('history')}>historique</button>
          <button className="lp-cta" onClick={() => setActiveTab('live')}>ouvrir la régie</button>
        </div>
      </nav>

      {/* ── Hero · appareil à droite, titre bas-de-casse à gauche ── */}
      <header className="lp-hero">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow">00 · RÉGIE DE PROJECTION</p>
          <h1 className="lp-title">
            la parole <em>s'affiche</em> pendant qu'elle se prêche.
          </h1>
          <p className="lp-lede">
            versepro écoute le prédicateur, reconnaît chaque référence biblique
            et prépare la projection — obs, vmix, propresenter, moniteur scène.
            le mode sûr exige une validation humaine. l'autopilote reste un choix explicite.
          </p>
          <div className="lp-actions">
            <button className="lp-btn-primary" onClick={() => setActiveTab('live')}>ouvrir la régie</button>
            <button className="lp-btn-ghost" onClick={() => setActiveTab('history')}>voir l'historique</button>
          </div>
        </div>

        {/* Produit · la régie est le visuel marketing */}
        <figure className="lp-console-preview" aria-label="Aperçu de la régie VersePro">
          <div className="lp-console-top">
            <div>
              <span>RÉGIE LIVE</span>
              <strong>À valider</strong>
            </div>
            <div className="lp-console-status">
              <span className={connected ? 'is-on' : ''} />
              {connected ? 'SERVEUR' : 'LOCAL'}
            </div>
          </div>

          <div className="lp-console-grid">
            <div className="lp-console-main">
              <div className="lp-console-transcript">
                <span>TRANSCRIPT DIRECT</span>
                <p>{currentTranscript || 'le signal reconnu apparaîtra ici pendant la prédication.'}</p>
              </div>

              <article className="lp-console-card">
                <div>
                  <strong>{previewPrimary?.reference || 'Aucune détection'}</strong>
                  <span>{onAir?.reference === previewPrimary?.reference ? 'DIRECT' : 'À VALIDER'}</span>
                </div>
                <p>{previewPrimary?.text || 'Les versets détectés apparaîtront dans cette file.'}</p>
                {previewPrimary?.reference && (
                  <button type="button" onClick={() => setActiveTab('live')}>ouvrir dans la régie</button>
                )}
              </article>

              {previewSecondary && (
                <article className="lp-console-card is-muted">
                  <div>
                    <strong>{previewSecondary.reference}</strong>
                    <span>EN ATTENTE</span>
                  </div>
                  <p>{previewSecondary.text}</p>
                </article>
              )}
            </div>

            <aside className="lp-console-side">
              <div>
                <span>ENTRÉE MICRO</span>
                <strong>{isListening ? 'signal en direct' : 'signal prêt'}</strong>
              </div>
              <div className="lp-console-micro-bars">
                {(isListening && waveform?.length ? waveform.slice(0, 22) : METER_BARS.slice(0, 22)).map((sample, i) => (
                  <span
                    key={i}
                    style={{ height: `${isListening ? Math.max(4, Math.abs(sample) * 52) : Math.max(6, Math.round(sample * 0.72))}px` }}
                  />
                ))}
              </div>
              <button type="button" onClick={() => setActiveTab('settings')}>choisir le micro</button>
              <div className="lp-console-output">
                <span>OBS</span>
                <span>vMix</span>
                <span>ProPresenter</span>
              </div>
            </aside>
          </div>
        </figure>
      </header>

      {/* ── Bande-mètre · lecture d'instrument, valeurs réelles ── */}
      <aside className="lp-meter" aria-label="Lecture du signal">
        <p className="lp-meter-label">ENTRÉE · 16 KHZ</p>
        <div className="lp-meter-bars">
          {METER_BARS.map((h, i) => (
            <span key={i} style={{ height: `${h}px`, opacity: 0.35 + (h / 28) * 0.65 }} />
          ))}
        </div>
        <p className="lp-meter-label">SEUIL VAD · 0.50</p>
      </aside>

      {/* ── Rangée de trois stats · chiffres réels, sérif, tabulaires ── */}
      <section className="lp-stats" aria-label="Chiffres clés">
        <div className="lp-stat">
          <strong>{semanticStatus?.verses_indexed ? semanticStatus.verses_indexed.toLocaleString('fr-FR') : 'corpus local'}</strong>
          <span className="lp-stat-label">VERSETS INDEXÉS</span>
        </div>
        <div className="lp-stat">
          <strong>{availableBibles.length}</strong>
          <span className="lp-stat-label">TRADUCTIONS BIBLIQUES</span>
        </div>
        <div className="lp-stat">
          <strong>humain</strong>
          <span className="lp-stat-label">VALIDATION AVANT ÉCRAN</span>
        </div>
      </section>

      {/* ── Chaîne de travail ── */}
      <section className="lp-flow" aria-label="Chaîne de travail">
        <h2 className="lp-h2">trois gestes, aucun stress.</h2>
        <div className="lp-flow-grid">
          <article className="lp-card">
            <span className="lp-flow-index">01</span>
            <h3>le micro entre, le texte sort.</h3>
            <p>le flux audio est transcrit en direct — avec deepgram, nemotron ou vosk. le prétraitement reste désactivable pour préserver une sortie console propre.</p>
          </article>
          <article className="lp-card">
            <span className="lp-flow-index">02</span>
            <h3>la machine propose, l'humain dispose.</h3>
            <p>les références détectées entrent dans une file de validation. seules les citations explicites et sûres peuvent se projeter seules — et seulement si vous l'activez.</p>
          </article>
          <article className="lp-card">
            <span className="lp-flow-index">03</span>
            <h3>une validation, toutes les sorties.</h3>
            <p>écran autonome, obs, vmix, propresenter, moniteur scène et téléphones de l'assemblée reçoivent la même scène au même instant.</p>
          </article>
        </div>
      </section>

      {/* ── Activité récente (données : casse naturelle) ── */}
      <section className="lp-recent" aria-label="Dernières écritures détectées">
        <h2 className="lp-h2">dernières écritures projetées.</h2>
        <div className="lp-recent-list">
          {recentVerses.length > 0 ? recentVerses.map((verse) => (
            <button key={verse.id} className="lp-recent-item" onClick={() => setActiveTab('history')}>
              <span className="lp-recent-ref">{verse.reference}</span>
              <span className="lp-recent-time">
                {new Date(verse.detected_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </button>
          )) : (
            <p className="lp-recent-empty">aucune détection pour l'instant — ouvrez la régie et parlez.</p>
          )}
        </div>
      </section>

      {/* ── Footer · Ft5 Statement ── */}
      <footer className="lp-footer">
        <p className="lp-footer-statement">l'opérateur garde la main. toujours.</p>
        <div className="lp-footer-meta">
          <span>VERSEPRO · V2</span>
          <span>{connected ? 'SERVEUR · PRÊT' : 'SERVEUR · HORS LIGNE'}</span>
          <span>{propresenterConnected ? 'PROPRESENTER · ACTIF' : 'PROPRESENTER · MANUEL'}</span>
          <span>{asrStatus?.nemotron?.ready || asrStatus?.vosk?.available ? 'MOTEUR LOCAL · PRÊT' : 'MODE LOCAL · À PRÉPARER'}</span>
        </div>
      </footer>
    </div>
  )
}
