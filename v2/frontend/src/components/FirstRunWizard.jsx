import React, { useEffect, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'

/*
 * Assistant de premier lancement — installe VersePro comme un vrai produit :
 * micro testé, reconnaissance vocale locale (Vosk) et intelligence (index
 * sémantique e5 · clé cloud · ou rien) téléchargées AVEC progression,
 * depuis les endpoints existants. Tout est optionnel, tout est repassable.
 */

const STEPS = ['bienvenue', 'micro', 'voix', 'intelligence', 'pret']

export default function FirstRunWizard({ onDone }) {
  const { updateSettings } = useStore()
  const [step, setStep] = useState(0)

  // ── Micro : test local (VU) sans toucher aux moteurs ──
  const [micState, setMicState] = useState('idle') // idle | asking | live | denied
  const [micLevel, setMicLevel] = useState(0)
  const micRefs = useRef({ stream: null, ctx: null, raf: null })

  const stopMicTest = () => {
    const { stream, ctx, raf } = micRefs.current
    if (raf) cancelAnimationFrame(raf)
    if (stream) stream.getTracks().forEach((t) => t.stop())
    if (ctx) ctx.close().catch(() => {})
    micRefs.current = { stream: null, ctx: null, raf: null }
  }

  const startMicTest = async () => {
    setMicState('asking')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      ctx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      micRefs.current = { stream, ctx, raf: null }
      const tick = () => {
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) { const d = (data[i] - 128) / 128; sum += d * d }
        setMicLevel(Math.min(100, Math.round(Math.sqrt(sum / data.length) * 400)))
        micRefs.current.raf = requestAnimationFrame(tick)
      }
      tick()
      setMicState('live')
    } catch {
      setMicState('denied')
    }
  }

  useEffect(() => () => stopMicTest(), [])
  useEffect(() => { if (STEPS[step] !== 'micro') stopMicTest() }, [step])

  // ── Vosk : statut + téléchargement avec progression ──
  const [vosk, setVosk] = useState(null)
  const pollVosk = async () => {
    try {
      const r = await fetch('/api/v1/vosk/status')
      setVosk(await r.json())
    } catch { setVosk(null) }
  }
  useEffect(() => {
    if (STEPS[step] !== 'voix') return
    pollVosk()
    const id = setInterval(pollVosk, 2500)
    return () => clearInterval(id)
  }, [step])

  // ── Sémantique : statut + préparation (téléchargement 118 Mo + index) ──
  const [sem, setSem] = useState(null)
  const [aiChoice, setAiChoice] = useState(null) // 'local' | 'cloud' | 'none'
  const [cloudKey, setCloudKey] = useState('')
  const [cloudSaved, setCloudSaved] = useState(false)
  const pollSem = async () => {
    try {
      const r = await fetch('/api/v1/semantic/status')
      setSem(await r.json())
    } catch { setSem(null) }
  }
  useEffect(() => {
    if (STEPS[step] !== 'intelligence') return
    pollSem()
    const id = setInterval(pollSem, 2500)
    return () => clearInterval(id)
  }, [step])

  const prepareSemantic = async () => {
    setAiChoice('local')
    try { await fetch('/api/v1/semantic/prepare', { method: 'POST' }); pollSem() } catch { /* bannière backend */ }
  }
  const saveCloudKey = async () => {
    const key = cloudKey.trim()
    if (!key) return
    const payload = key.startsWith('sk-or-') ? { openrouter_api_key: key } : { deepgram_api_key: key }
    const res = await updateSettings(payload)
    if (res) { setCloudSaved(true); setAiChoice('cloud') }
  }

  const finish = () => {
    stopMicTest()
    try {
      localStorage.setItem('versepro_first_run_done', 'true')
      localStorage.setItem('versepro_onboarding_ignored', 'true')
      localStorage.setItem('versepro_last_tab', 'live')
    } catch { /* stockage privé */ }
    onDone()
  }

  const stepLabel = ['ACCUEIL', 'MICRO', 'VOIX LOCALE', 'INTELLIGENCE', 'PRÊT'][step]
  const voskReady = Boolean(vosk?.installed)
  const semReady = Boolean(sem?.installed)
  const semBusy = Boolean(sem && (sem.downloading || sem.indexing))

  return (
    <div className="fw-backdrop" role="dialog" aria-modal="true" aria-label="Premier lancement">
      <div className="fw-panel">
        <header className="fw-head">
          <span className="fw-brand">versepro</span>
          <span className="fw-step-label">{`0${step + 1} · ${stepLabel}`}</span>
        </header>

        <div className="fw-progress" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s} className={i <= step ? 'is-done' : ''} />)}
        </div>

        <main className="fw-body">
          {STEPS[step] === 'bienvenue' && (
            <>
              <h1 className="fw-title">la régie s'installe en trois minutes.</h1>
              <p className="fw-lede">
                on teste votre micro, puis versepro télécharge ce qu'il lui faut pour
                fonctionner <strong>sans internet le dimanche</strong> — reconnaissance
                vocale et intelligence locales. chaque étape est optionnelle.
              </p>
            </>
          )}

          {STEPS[step] === 'micro' && (
            <>
              <h1 className="fw-title">le micro, d'abord.</h1>
              <p className="fw-lede">autorisez l'accès et parlez : la barre doit bouger.</p>
              {micState !== 'live' ? (
                <button className="vp-btn vp-btn--primary" onClick={startMicTest} disabled={micState === 'asking'}>
                  {micState === 'asking' ? 'demande en cours…' : 'tester le micro'}
                </button>
              ) : (
                <div className="fw-vu" role="meter" aria-valuenow={micLevel} aria-valuemin={0} aria-valuemax={100}>
                  <div style={{ width: `${micLevel}%` }} />
                </div>
              )}
              {micState === 'live' && micLevel > 8 && <p className="fw-ok"><Icon name="check" size={13} /> signal reçu — micro opérationnel</p>}
              {micState === 'denied' && (
                <p className="fw-warn">accès refusé — autorisez le micro dans les réglages du navigateur, ou continuez : vous pourrez le faire plus tard.</p>
              )}
            </>
          )}

          {STEPS[step] === 'voix' && (
            <>
              <h1 className="fw-title">la voix devient du texte, en local.</h1>
              <p className="fw-lede">
                le modèle vosk transcrit la prédication sans connexion. il se télécharge
                une seule fois{vosk?.model_type ? ` (modèle ${vosk.model_type})` : ''}.
              </p>
              {voskReady ? (
                <p className="fw-ok"><Icon name="check" size={13} /> modèle vocal installé et prêt</p>
              ) : vosk?.downloading ? (
                <div className="fw-dl">
                  <span className="fw-dl-label">TÉLÉCHARGEMENT EN COURS…</span>
                  <div className="fw-bar is-indeterminate"><div /></div>
                </div>
              ) : (
                <button className="vp-btn vp-btn--primary" onClick={async () => { await fetch('/api/v1/vosk/download', { method: 'POST' }); pollVosk() }}>
                  télécharger le modèle vocal
                </button>
              )}
              <p className="fw-hint">vous utilisez deepgram cloud ? cette étape reste utile : vosk prend le relais si internet tombe en plein culte.</p>
            </>
          )}

          {STEPS[step] === 'intelligence' && (
            <>
              <h1 className="fw-title">et quand le prédicateur ne cite pas ?</h1>
              <p className="fw-lede">« il a marché sur l'eau » → matthieu 14. choisissez comment versepro comprend les paraphrases :</p>
              <div className="fw-choices">
                <button className={`fw-choice ${aiChoice === 'local' || semReady ? 'is-active' : ''}`} onClick={prepareSemantic} disabled={semBusy}>
                  <span className="fw-choice-tag">RECOMMANDÉ · 118 MO</span>
                  <strong>intelligence locale</strong>
                  <p>index sémantique hors-ligne. privé, gratuit, 6 ms par phrase.</p>
                  {semReady && <span className="fw-ok"><Icon name="check" size={12} /> prêt ({sem.verses_total} versets)</span>}
                  {semBusy && (
                    <span className="fw-dl-label">
                      {sem.downloading ? `TÉLÉCHARGEMENT ${Math.round(sem.download_progress || 0)} %` : `INDEXATION ${sem.verses_indexed || 0} VERSETS…`}
                    </span>
                  )}
                </button>
                <div className={`fw-choice ${cloudSaved ? 'is-active' : ''}`}>
                  <span className="fw-choice-tag">CLOUD · CLÉ REQUISE</span>
                  <strong>clé deepgram / openrouter</strong>
                  <div className="fw-key-row">
                    <input className="vp-input" type="password" placeholder="dg_… ou sk-or-…" value={cloudKey} onChange={(e) => setCloudKey(e.target.value)} />
                    <button className="vp-btn vp-btn--sm" onClick={saveCloudKey} disabled={!cloudKey.trim()}>ok</button>
                  </div>
                  {cloudSaved && <span className="fw-ok"><Icon name="check" size={12} /> clé enregistrée</span>}
                </div>
                <button className={`fw-choice ${aiChoice === 'none' ? 'is-active' : ''}`} onClick={() => setAiChoice('none')}>
                  <span className="fw-choice-tag">MINIMAL</span>
                  <strong>sans intelligence</strong>
                  <p>les citations explicites (« jean 3 verset 16 ») marchent déjà parfaitement.</p>
                </button>
              </div>
            </>
          )}

          {STEPS[step] === 'pret' && (
            <>
              <h1 className="fw-title">c'est prêt.</h1>
              <ul className="fw-recap">
                <li><Icon name={micState === 'live' ? 'check' : 'alert'} size={13} /> micro {micState === 'live' ? 'testé' : 'à tester dans la régie'}</li>
                <li><Icon name={voskReady ? 'check' : 'alert'} size={13} /> voix locale {voskReady ? 'installée' : 'non installée (cloud requis)'}</li>
                <li><Icon name={semReady || cloudSaved ? 'check' : 'alert'} size={13} /> intelligence {semReady ? 'locale prête' : cloudSaved ? 'cloud configurée' : 'désactivée'}</li>
              </ul>
              <p className="fw-lede">tout se règle à nouveau dans <strong>paramètres</strong>, à tout moment.</p>
            </>
          )}
        </main>

        <footer className="fw-foot">
          <button className="vp-btn vp-btn--ghost" onClick={finish}>passer</button>
          <div className="fw-foot-right">
            {step > 0 && <button className="vp-btn" onClick={() => setStep(step - 1)}>retour</button>}
            {step < STEPS.length - 1 ? (
              <button className="vp-btn vp-btn--primary" onClick={() => setStep(step + 1)}>continuer</button>
            ) : (
              <button className="vp-btn vp-btn--primary" onClick={finish}>ouvrir la régie</button>
            )}
          </div>
        </footer>
      </div>
    </div>
  )
}
