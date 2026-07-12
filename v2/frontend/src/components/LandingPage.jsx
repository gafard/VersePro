import React, { useMemo } from 'react'
import { useStore } from '../store.js'

export default function LandingPage({ setActiveTab }) {
  const { history, connected, propresenterConnected } = useStore()

  const recentVerses = useMemo(() => history.slice(0, 3), [history])

  return (
    <div className="landing-shell">
      {/* Navigation supérieure de la landing */}
      <nav className="landing-nav">
        <button className="landing-brand" onClick={() => setActiveTab('home')} aria-label="VersePro accueil">
          <span className="landing-brand-mark">V</span>
          <span>VersePro</span>
        </button>

        <div className="landing-nav-links" aria-label="Navigation principale">
          <button onClick={() => setActiveTab('live')}>Régie</button>
          <button onClick={() => setActiveTab('history')}>Historique</button>
          <button onClick={() => setActiveTab('statistics')}>Rapports</button>
        </div>

        <button className="landing-nav-cta" onClick={() => setActiveTab('live')}>
          Lancer la régie
        </button>
      </nav>

      {/* Hero Section asymétrique */}
      <main className="landing-hero">
        <section className="landing-copy" aria-labelledby="landing-title">
          <p className="landing-kicker">Moteur de projection sémantique</p>
          <h1 id="landing-title">Le cerveau de votre projection</h1>
          <p className="landing-subtitle">
            VersePro écoute le prédicateur, extrait les références bibliques à la volée 
            et pilote toutes vos sorties vidéo (OBS, vMix, ProPresenter et moniteurs scène) 
            en maintenant l'opérateur humain au centre des décisions.
          </p>
          <div className="landing-actions">
            <button className="vp-btn vp-btn--primary" onClick={() => setActiveTab('live')}>
              Ouvrir la régie
            </button>
            <button className="vp-btn vp-btn--ghost" onClick={() => setActiveTab('history')}>
              Parcourir l'historique
            </button>
          </div>
        </section>

        {/* Schéma fonctionnel du Pipeline (remplace le faux chrome) */}
        <section className="landing-pipeline-display" aria-label="Architecture de détection VersePro">
          <div className="pipeline-card">
            <div className="pipeline-card-header">
              <span className="pipeline-dot" />
              <span className="pipeline-mono">PIPELINE SÉMANTIQUE ACTIF</span>
            </div>
            
            <div className="pipeline-flow">
              <div className="pipeline-step">
                <div className="step-num">01</div>
                <div className="step-content">
                  <strong>Transcription</strong>
                  <span className="step-meta">Vosk Local / Deepgram</span>
                  <div className="step-visual-audio">
                    <span style={{ height: '6px' }} />
                    <span style={{ height: '14px' }} />
                    <span style={{ height: '22px' }} />
                    <span style={{ height: '8px' }} />
                    <span style={{ height: '18px' }} />
                  </div>
                </div>
              </div>

              <div className="pipeline-step">
                <div className="step-num">02</div>
                <div className="step-content">
                  <strong>Analyse IA</strong>
                  <span className="step-meta">Parser local & validation</span>
                  <div className="step-badge">CONFIDENCE 98%</div>
                </div>
              </div>

              <div className="pipeline-step">
                <div className="step-num">03</div>
                <div className="step-content">
                  <strong>Routage</strong>
                  <span className="step-meta">OBS, vMix, ProPresenter</span>
                  <div className="step-visual-outputs">
                    <span>OBS</span>
                    <span>vMix</span>
                    <span>ProPresenter</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Sections du Workflow de détection (remplace les Proof Cards clichés) */}
      <section className="landing-workflow" aria-label="Workflow de validation">
        <div className="workflow-card">
          <span className="workflow-number">01</span>
          <h3>Écoute & Analyse</h3>
          <p>Le flux audio du microphone est analysé en temps réel avec une latence inférieure à 5 ms.</p>
        </div>

        <div className="workflow-card">
          <span className="workflow-number">02</span>
          <h3>Suggestion intelligente</h3>
          <p>Les versets mentionnés indirectement sont isolés et présentés pour validation, sans jamais s'afficher automatiquement.</p>
        </div>

        <div className="workflow-card">
          <span className="workflow-number">03</span>
          <h3>Diffusion universelle</h3>
          <p>La validation envoie instantanément la scène vers vos sorties de diffusion paramétrées.</p>
        </div>

        <div className="workflow-card workflow-status">
          <span className="workflow-number">SYS</span>
          <h3>Statut Système</h3>
          <div className="status-grid">
            <div>Serveur : <strong className={connected ? 'text-ok' : 'text-bad'}>{connected ? 'Prêt' : 'Déconnecté'}</strong></div>
            <div>Pont ProPresenter : <strong className={propresenterConnected ? 'text-ok' : 'text-faint'}>{propresenterConnected ? 'Actif' : 'Manuel'}</strong></div>
          </div>
        </div>
      </section>

      {/* Historique récent des écritures */}
      <section className="landing-recent-band" aria-label="Dernières écritures détectées">
        <div className="recent-header">
          <span className="landing-section-label">Activité récente</span>
          <h2>Dernières écritures projetées lors des cultes</h2>
        </div>

        <div className="landing-recent-list">
          {recentVerses.length > 0 ? recentVerses.map((verse) => (
            <button key={verse.id} className="landing-recent-item" onClick={() => setActiveTab('history')}>
              <span className="recent-ref">{verse.reference}</span>
              <span className="recent-time">
                {new Date(verse.detected_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </button>
          )) : (
            ['Jean 3:16', 'Psaume 23:1', 'Romains 8:28'].map((reference) => (
              <button key={reference} className="landing-recent-item" onClick={() => setActiveTab('live')}>
                <span className="recent-ref">{reference}</span>
                <span className="recent-time">démo</span>
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
