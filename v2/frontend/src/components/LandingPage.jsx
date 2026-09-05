import React, { useMemo } from 'react'
import { shallow } from 'zustand/shallow'
import { useStore } from '../store.js'
import pastorLiveWide from '../assets/landing/pastor-live-wide.jpg'
import pastorTeachingPortrait from '../assets/landing/pastor-teaching-portrait.jpg'

/* Hallmark · pre-emit critique: P5 H5 E4 S5 R4 V5 */

const RELEASE_URL = 'https://github.com/gafard/VersePro/releases/latest'
const SOURCE_URL = 'https://github.com/gafard/VersePro'
const SUPPORT_URL = 'mailto:gnane.gafard@gmail.com?subject=Soutenir%20VersePro'

const METER_BARS = Array.from({ length: 72 }, (_, index) => {
  const envelope = Math.sin((index / 71) * Math.PI)
  const pulse = 0.55 + (Math.sin(index * 1.7) * Math.sin(index * 0.31) * 0.45)
  return Math.round(6 + envelope * pulse * 28)
})

const FALLBACK_TRANSCRIPT = 'Car Dieu a tant aimé le monde qu’il a donné son Fils unique afin que quiconque croit en lui ne périsse point mais qu’il ait la vie éternelle.'

export default function LandingPage({ setActiveTab }) {
  const {
    connected,
    availableBibles,
    semanticStatus,
    currentTranscript,
    onAir,
    isListening,
    waveform
  } = useStore((state) => ({
    connected: state.connected,
    availableBibles: state.availableBibles,
    semanticStatus: state.semanticStatus,
    currentTranscript: state.currentTranscript,
    onAir: state.onAir,
    isListening: state.isListening,
    waveform: state.waveform
  }), shallow)

  const liveReference = onAir?.reference || 'Jean 3:16'
  const liveText = onAir?.text || FALLBACK_TRANSCRIPT
  const transcriptWords = useMemo(
    () => (currentTranscript || FALLBACK_TRANSCRIPT).split(/\s+/).slice(0, 28),
    [currentTranscript]
  )
  const indexedVerses = semanticStatus?.verses_indexed
    ? semanticStatus.verses_indexed.toLocaleString('fr-FR')
    : '31 102'
  const bibleCount = availableBibles?.length || 7

  const openRegie = () => setActiveTab('live')

  return (
    <div className="lp">
      <nav className="lp-nav" aria-label="Navigation principale">
        <button className="lp-wordmark" type="button" onClick={() => setActiveTab('home')}>
          <img src="/icons/icon-192.png" alt="" aria-hidden="true" />
          <span>VersePro</span>
        </button>
        <div className="lp-nav-links">
          <a href="#experience">Le direct</a>
          <a href="#fonctionnement">Fonctionnement</a>
          <a href="#soutenir">Soutenir</a>
        </div>
        <a className="lp-cta" href={RELEASE_URL} target="_blank" rel="noreferrer">
          Télécharger <span aria-hidden="true">↓</span>
        </a>
      </nav>

      <main>
        <header className="lp-hero">
          <img className="lp-hero-photo" src={pastorLiveWide} alt="Pasteur s'adressant à son assemblée pendant un culte" />
          <div className="lp-hero-shade" aria-hidden="true" />
          <div className="lp-hero-copy">
            <p className="lp-eyebrow"><span /> Projection biblique en temps réel</p>
            <h1>VersePro</h1>
            <p className="lp-hero-line">La Parole apparaît pendant qu’elle se prêche.</p>
            <p className="lp-lede">
              VersePro écoute, retrouve la référence et prépare l’écran. Le régisseur valide.
              L’assemblée lit. Même quand Internet ne suit plus.
            </p>
            <div className="lp-actions">
              <a className="lp-btn-primary" href={RELEASE_URL} target="_blank" rel="noreferrer">
                Télécharger gratuitement <span aria-hidden="true">↓</span>
              </a>
              <button className="lp-btn-ghost" type="button" onClick={openRegie}>
                Ouvrir la régie <span aria-hidden="true">→</span>
              </button>
            </div>
            <div className="lp-hero-meta" aria-label="Caractéristiques principales">
              <span>macOS + Windows</span>
              <span>mode local</span>
              <span>don libre</span>
            </div>
          </div>

          <div className="lp-hero-status" aria-label="État de la démonstration">
            <span className={connected ? 'is-online' : ''} />
            {connected ? 'Régie connectée' : 'Démo en direct'}
          </div>

          <div className="lp-hero-lowerthird" aria-label={`Aperçu de projection : ${liveReference}`}>
            <div className="lp-lowerthird-signal" aria-hidden="true">
              {(isListening && waveform?.length ? waveform.slice(0, 28) : METER_BARS.slice(0, 28)).map((sample, index) => (
                <span
                  key={index}
                  style={{
                    '--meter-height': `${isListening ? Math.max(5, Math.abs(sample) * 34) : Math.max(5, Math.round(sample * 0.55))}px`,
                    '--meter-delay': `${index * -60}ms`
                  }}
                />
              ))}
            </div>
            <div className="lp-lowerthird-copy">
              <p>{liveText}</p>
              <strong>{liveReference} <span>LSG</span></strong>
            </div>
          </div>

          <a className="lp-hero-next" href="#experience">
            Voir VersePro en action <span aria-hidden="true">↓</span>
          </a>
        </header>

        <section className="lp-marquee" aria-label="Chaîne de travail VersePro">
          <div>
            <span>le micro écoute</span><i>→</i><span>le texte remonte</span><i>→</i>
            <span>l’opérateur valide</span><i>→</i><span>la salle lit</span><i>→</i>
            <span aria-hidden="true">le micro écoute</span><i aria-hidden="true">→</i>
            <span aria-hidden="true">le texte remonte</span><i aria-hidden="true">→</i>
            <span aria-hidden="true">l’opérateur valide</span><i aria-hidden="true">→</i>
            <span aria-hidden="true">la salle lit</span>
          </div>
        </section>

        <section id="experience" className="lp-experience">
          <div className="lp-section-heading">
            <p className="lp-eyebrow">01 · À l’antenne</p>
            <h2>Le direct devient lisible.</h2>
            <p>
              Pas une animation abstraite : la voix entre, la transcription avance et le verset
              sort dans un habillage prêt pour l’écran, OBS ou vMix.
            </p>
          </div>

          <div className="lp-broadcast-layout">
            <figure className="lp-broadcast-stage">
              <img src={pastorTeachingPortrait} alt="Prédicatrice enseignant avec une Bible ouverte" />
              <figcaption className="lp-broadcast-caption">
                <p>« Ta parole est une lampe à mes pieds, et une lumière sur mon sentier. »</p>
                <strong>Psaume 119:105 <span>LSG</span></strong>
              </figcaption>
              <div className="lp-broadcast-live"><span /> DIRECT</div>
            </figure>

            <div className="lp-prompter" aria-label="Transcription simulée en direct">
              <div className="lp-prompter-head">
                <span>TRANSCRIPT DIRECT</span>
                <strong><i /> MICRO ACTIF</strong>
              </div>
              <div className="lp-prompter-window">
                <p>
                  {transcriptWords.map((word, index) => (
                    <span className={index > 15 ? 'is-current' : ''} key={`${word}-${index}`}>{word} </span>
                  ))}
                </p>
              </div>
              <div className="lp-prompter-detection">
                <div>
                  <span>RÉFÉRENCE DÉTECTÉE</span>
                  <strong>{liveReference}</strong>
                </div>
                <button type="button" onClick={openRegie}>Valider <span aria-hidden="true">→</span></button>
              </div>
              <div className="lp-prompter-meter" aria-hidden="true">
                {METER_BARS.map((height, index) => (
                  <span key={index} style={{ '--meter-height': `${height}px`, '--meter-delay': `${index * -45}ms` }} />
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="fonctionnement" className="lp-workflow">
          <div className="lp-section-heading is-wide">
            <p className="lp-eyebrow">02 · Pensé pour le dimanche</p>
            <h2>Un instrument de régie, pas un pari sur l’IA.</h2>
          </div>
          <div className="lp-workflow-list">
            <article>
              <span>01</span>
              <h3>Écouter</h3>
              <p>Deepgram dans le cloud ou moteur local hors connexion. L’entrée audio reste visible et contrôlable.</p>
            </article>
            <article>
              <span>02</span>
              <h3>Proposer</h3>
              <p>Les références explicites et les rapprochements sémantiques arrivent séparément, avec leur niveau de confiance.</p>
            </article>
            <article>
              <span>03</span>
              <h3>Valider</h3>
              <p>Le mode sûr garde une personne entre la détection et l’écran public. L’autopilote reste un choix explicite.</p>
            </article>
            <article>
              <span>04</span>
              <h3>Diffuser</h3>
              <p>Écran autonome, lower third, OBS, vMix, ProPresenter et retour scène partagent la même scène.</p>
            </article>
          </div>
        </section>

        <section className="lp-proof" aria-label="Capacités locales de VersePro">
          <div><strong>{indexedVerses}</strong><span>versets indexés localement</span></div>
          <div><strong>{bibleCount}</strong><span>traductions disponibles</span></div>
          <div><strong>humain</strong><span>validation avant écran</span></div>
        </section>

        <section id="telecharger" className="lp-download">
          <div className="lp-download-copy">
            <p className="lp-eyebrow">03 · Disponible gratuitement</p>
            <h2>Télécharger. Installer. Projeter.</h2>
            <p>
              VersePro est un logiciel indépendant. La page de la dernière version contient les
              installateurs disponibles, les notes de version et les fichiers de vérification.
            </p>
            <div className="lp-actions">
              <a className="lp-btn-primary" href={RELEASE_URL} target="_blank" rel="noreferrer">
                Voir la dernière version <span aria-hidden="true">↗</span>
              </a>
              <a className="lp-btn-ghost" href={SOURCE_URL} target="_blank" rel="noreferrer">
                Consulter le code source <span aria-hidden="true">↗</span>
              </a>
            </div>
          </div>
          <div className="lp-download-ledger" aria-label="Disponibilité de VersePro">
            <div><span>macOS</span><strong>Application native</strong></div>
            <div><span>Windows</span><strong>Application native</strong></div>
            <div><span>Licence</span><strong>Gratuit · don libre</strong></div>
            <div><span>Version</span><strong>VersePro V2</strong></div>
          </div>
        </section>

        <aside id="soutenir" className="lp-support">
          <p className="lp-eyebrow">04 · Faire durer le projet</p>
          <h2>Gratuit pour les églises. Soutenu par celles qui le peuvent.</h2>
          <p>
            Les dons servent aux signatures des applications, aux tests sur plusieurs machines,
            à l’hébergement des mises à jour et au développement des moteurs locaux.
          </p>
          <a className="lp-btn-support" href={SUPPORT_URL}>
            Soutenir VersePro <span aria-hidden="true">→</span>
          </a>
        </aside>
      </main>

      <footer className="lp-footer">
        <div className="lp-footer-brand">
          <img src="/icons/icon-192.png" alt="" aria-hidden="true" />
          <strong>VersePro</strong>
          <span>par Selah Studios</span>
        </div>
        <p>L’opérateur garde la main. Toujours.</p>
        <div className="lp-footer-links">
          <a href={RELEASE_URL} target="_blank" rel="noreferrer">Télécharger</a>
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">Code source</a>
          <a href={SUPPORT_URL}>Soutenir</a>
        </div>
      </footer>
    </div>
  )
}
