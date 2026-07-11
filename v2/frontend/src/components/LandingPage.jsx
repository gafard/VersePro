import React, { useMemo } from 'react'
import { useStore } from '../store.js'
import landingPack from '../assets/versepro-landing-pack.png'

export default function LandingPage({ setActiveTab }) {
  const { history, connected, propresenterConnected } = useStore()

  const recentVerses = useMemo(() => history.slice(0, 3), [history])

  const proofCards = [
    {
      title: 'Demarrage calme',
      value: '1 clic',
      text: 'La regie s ouvre sans terminal et sans chasse aux ports.'
    },
    {
      title: 'Analyse prudente',
      value: '95%',
      text: 'Les deductions IA restent a valider avant diffusion.'
    },
    {
      title: 'Direct protege',
      value: '< 5 ms',
      text: 'Les references explicites gardent la priorite.'
    }
  ]

  return (
    <div className="landing-shell">
      <nav className="landing-nav">
        <button className="landing-brand" onClick={() => setActiveTab('home')} aria-label="VersePro accueil">
          <span className="landing-brand-mark">VP</span>
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
          <p className="landing-kicker">Assistant de projection biblique</p>
          <h1 id="landing-title">VersePro</h1>
          <p className="landing-subtitle">
            L'assistant discret des cultes en direct. Il ecoute, reconnait les references,
            prepare la projection et laisse toujours le regisseur garder la main.
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
          <img src={landingPack} alt="" className="landing-pack-image" />

          <div className="landing-note landing-note-left">
            <span>Avant</span>
            <p>Terminal, cles API, ports, stress.</p>
          </div>

          <div className="landing-note landing-note-right">
            <span>Apres</span>
            <p>Une regie prete, lisible, prudente.</p>
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
