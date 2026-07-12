import React, { useMemo } from 'react'
import { useStore } from '../store.js'

export default function LandingPage({ setActiveTab }) {
  const { history, connected, propresenterConnected } = useStore()

  const recentVerses = useMemo(() => history.slice(0, 3), [history])

  const proofCards = [
    {
      title: 'Mode',
      value: 'Direct sécurisé',
      text: 'Les références explicites passent en priorité, l IA reste prudente.'
    },
    {
      title: 'Fonctionnement',
      value: 'Hors ligne',
      text: 'Vosk permet de tester et d utiliser la régie sans clé cloud.'
    },
    {
      title: 'Projection',
      value: '< 5 ms',
      text: 'Le parser local répond avant que l opérateur perde le fil.'
    },
    {
      title: 'Analyse',
      value: 'Validation humaine',
      text: 'Les suggestions sémantiques arrivent dans À valider, jamais en direct.'
    }
  ]

  return (
    <div className="landing-shell">
      <nav className="landing-nav">
        <button className="landing-brand" onClick={() => setActiveTab('home')} aria-label="VersePro accueil">
          <span className="landing-brand-mark">V</span>
          <span>VersePro</span>
        </button>

        <div className="landing-nav-links" aria-label="Navigation principale">
          <button onClick={() => setActiveTab('live')}>Regie</button>
          <button onClick={() => setActiveTab('history')}>Historique</button>
          <button onClick={() => setActiveTab('statistics')}>Rapports</button>
        </div>

        <button className="landing-nav-cta" onClick={() => setActiveTab('live')}>
          Ouvrir
        </button>
      </nav>

      <main className="landing-hero">
        <div className="landing-sky-particles" aria-hidden="true" />

        <section className="landing-copy" aria-labelledby="landing-title">
          <p className="landing-kicker">Semantic projection engine</p>
          <h1 id="landing-title">VersePro</h1>
          <p className="landing-subtitle">
            The operating system for church media teams. VersePro écoute la prédication,
            prépare les Écritures en temps réel et garde la décision humaine au centre.
          </p>
          <div className="landing-actions">
            <button className="landing-primary" onClick={() => setActiveTab('live')}>
              Lancer la regie
            </button>
            <button className="landing-secondary" onClick={() => setActiveTab('history')}>
              Voir les detections
            </button>
          </div>
        </section>

        <section className="landing-pack-stage" aria-label="Apercu VersePro">
          <div className="landing-product-window">
            <div className="landing-window-bar">
              <div className="landing-window-dots" aria-hidden="true">
                <span /><span /><span />
              </div>
              <strong>Live</strong>
              <small>127.0.0.1:3001</small>
            </div>

            <div className="landing-window-body">
              <aside className="landing-window-sidebar" aria-hidden="true">
                <span className="landing-mini-logo">V</span>
                <i className="is-active" />
                <i />
                <i />
              </aside>

              <div className="landing-window-main">
                <div className="landing-window-status">
                  <span><i />Serveur</span>
                  <span><i />Deepgram</span>
                  <span><i />IA active</span>
                </div>

                <div className="landing-window-grid">
                  <div className="landing-window-queue">
                    <div className="landing-window-section-title">
                      <span>À valider</span>
                      <strong>3</strong>
                    </div>
                    <div className="landing-window-card is-local">
                      <div><strong>Jean 3:16</strong><small>Direct</small></div>
                      <p>Car Dieu a tant aimé le monde...</p>
                      <button>Projeter</button>
                    </div>
                    <div className="landing-window-card is-ai">
                      <div><strong>Romains 8:28</strong><small>Copilote 96%</small></div>
                      <p>Suggestion sémantique, validation requise.</p>
                      <button>Valider</button>
                    </div>
                  </div>

                  <div className="landing-window-air">
                    <span>À l'antenne</span>
                    <strong>Psaume 23:1</strong>
                    <p>L'Éternel est mon berger...</p>
                  </div>
                </div>

                <div className="landing-window-ticker">
                  <canvas aria-hidden="true" />
                  <span>... lisons ensemble dans l'évangile de Jean chapitre trois ...</span>
                  <button>LIVE</button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <section className="landing-proof-strip" aria-label="Points de fiabilite">
        {proofCards.map((card) => (
          <button key={card.title} className="landing-proof-card" onClick={() => setActiveTab('live')}>
            <span>{card.title}</span>
            <strong>{card.value}</strong>
            <p>{card.text}</p>
          </button>
        ))}

        <div className="landing-proof-card landing-status-card">
          <span>Etat systeme</span>
          <strong>{connected ? 'Pret' : 'Hors ligne'}</strong>
          <p>{propresenterConnected ? 'ProPresenter connecte.' : 'Projection manuelle disponible.'}</p>
        </div>
      </section>

      <section className="landing-recent-band" aria-label="Historique récent">
        <div>
          <span className="landing-section-label">Dernières détections</span>
          <h2>Dernières écritures détectées lors du culte</h2>
        </div>

        <div className="landing-recent-list">
          {recentVerses.length > 0 ? recentVerses.map((verse) => (
            <button key={verse.id} className="landing-recent-item" onClick={() => setActiveTab('history')}>
              <span>{verse.reference}</span>
              <small>
                {new Date(verse.detected_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </small>
            </button>
          )) : (
            ['Jean 3:16', 'Psaume 23:1', 'Romains 8:28'].map((reference) => (
              <button key={reference} className="landing-recent-item" onClick={() => setActiveTab('live')}>
                <span>{reference}</span>
                <small>demo</small>
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
