import React, { useEffect, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'

/*
 * Installateur de premier lancement — trois étapes, comme un vrai setup :
 * 1. INSTALLATION : scan automatique des composants IA, un seul bouton
 *    installe tout ce qui manque (vosk 1,4 Go + index sémantique e5 118 Mo)
 *    avec progression et erreurs visibles. L'index lexical est déjà inclus.
 * 2. MICRO : test du signal.
 * 3. PRÊT : récapitulatif + clé Deepgram optionnelle pour le cloud.
 */

const STEPS = ['installation', 'micro', 'pret']

export default function FirstRunWizard({ onDone }) {
  const { updateSettings } = useStore()
  const [step, setStep] = useState(0)

  // ── Scan + téléchargement des composants IA ──
  const [vosk, setVosk] = useState(null)
  const [sem, setSem] = useState(null)
  const [scanned, setScanned] = useState(false)
  const [backendDown, setBackendDown] = useState(false)
  const [launched, setLaunched] = useState(false)
  const autoAdvanced = useRef(false)

  const pollStatuses = async () => {
    try {
      const [vr, sr] = await Promise.all([
        fetch('/api/v1/vosk/status'),
        fetch('/api/v1/semantic/status')
      ])
      setVosk(await vr.json())
      setSem(await sr.json())
      setBackendDown(false)
    } catch {
      setBackendDown(true)
    } finally {
      setScanned(true)
    }
  }

  // Le sondage tourne tant que l'installateur est ouvert : les téléchargements
  // lancés à l'étape 1 restent visibles même si l'utilisateur avance.
  useEffect(() => {
    pollStatuses()
    const id = setInterval(pollStatuses, 2000)
    return () => clearInterval(id)
  }, [])

  const voskReady = Boolean(vosk?.installed)
  const semReady = Boolean(sem?.installed)
  const voskBusy = Boolean(vosk?.downloading)
  const semBusy = Boolean(sem && (sem.downloading || sem.indexing))
  const allReady = voskReady && semReady
  const anyBusy = voskBusy || semBusy
  const missing = [!voskReady && 'vosk', !semReady && 'sem'].filter(Boolean)

  const installVosk = async () => {
    try { await fetch('/api/v1/vosk/download', { method: 'POST' }) } catch { setBackendDown(true) }
  }
  const installSem = async () => {
    try { await fetch('/api/v1/semantic/prepare', { method: 'POST' }) } catch { setBackendDown(true) }
  }
  const installMissing = async () => {
    setLaunched(true)
    await Promise.all([!voskReady && installVosk(), !semReady && installSem()].filter(Boolean))
    pollStatuses()
  }

  // Quand l'installation lancée ici se termine, on passe au micro tout seul.
  useEffect(() => {
    if (launched && allReady && !autoAdvanced.current && STEPS[step] === 'installation') {
      autoAdvanced.current = true
      const t = setTimeout(() => setStep(1), 1400)
      return () => clearTimeout(t)
    }
  }, [launched, allReady, step])

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

  // ── Clé cloud optionnelle (étape finale) ──
  const [cloudKey, setCloudKey] = useState('')
  const [cloudSaved, setCloudSaved] = useState(false)
  const saveCloudKey = async () => {
    const key = cloudKey.trim()
    if (!key) return
    const payload = key.startsWith('sk-or-') ? { openrouter_api_key: key } : { deepgram_api_key: key }
    const res = await updateSettings(payload)
    if (res) setCloudSaved(true)
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

  const stepLabel = ['INSTALLATION', 'MICRO', 'PRÊT'][step]

  const componentRow = (label, size, ready, busy, busyLabel, progress, error, retry) => (
    <div className={`fw-comp ${ready ? 'is-ready' : ''}`}>
      <div className="fw-comp-head">
        <strong>{label}</strong>
        <span className="fw-comp-size">{size}</span>
      </div>
      {ready ? (
        <span className="fw-ok"><Icon name="check" size={12} /> installé</span>
      ) : busy ? (
        <div className="fw-dl">
          <span className="fw-dl-label">{busyLabel}</span>
          <div className={`fw-bar ${progress == null ? 'is-indeterminate' : ''}`}>
            <div style={progress == null ? undefined : { width: `${progress}%`, height: '100%', background: 'var(--color-accent)' }} />
          </div>
        </div>
      ) : error ? (
        <div>
          <p className="fw-warn">{error}</p>
          <button className="vp-btn vp-btn--sm" onClick={retry}>réessayer</button>
        </div>
      ) : (
        <span className="fw-comp-size">en attente d'installation</span>
      )}
    </div>
  )

  return (
    <div className="fw-backdrop" role="dialog" aria-modal="true" aria-label="Installation de VersePro">
      <div className="fw-panel">
        <header className="fw-head">
          <span className="fw-brand">versepro</span>
          <span className="fw-step-label">{`0${step + 1} · ${stepLabel}`}</span>
        </header>

        <div className="fw-progress" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s} className={i <= step ? 'is-done' : ''} />)}
        </div>

        <main className="fw-body">
          {STEPS[step] === 'installation' && (
            <>
              <h1 className="fw-title">installation des composants.</h1>
              <p className="fw-lede">
                versepro vérifie ce qui est présent sur cette machine et télécharge
                le reste — une seule fois. ensuite, tout fonctionne
                <strong> sans internet le dimanche</strong>.
              </p>

              {backendDown && (
                <p className="fw-warn">
                  le moteur versepro ne répond pas. lancez le backend puis{' '}
                  <button className="vp-btn vp-btn--sm" onClick={pollStatuses}>réessayer</button>
                </p>
              )}

              {!backendDown && !scanned && <p className="fw-hint">analyse de la machine…</p>}

              {scanned && !backendDown && (
                <div className="fw-comps">
                  <div className="fw-comp is-ready">
                    <div className="fw-comp-head">
                      <strong>index lexical des citations</strong>
                      <span className="fw-comp-size">inclus · 0 Mo</span>
                    </div>
                    <span className="fw-ok"><Icon name="check" size={12} /> « jean 3 verset 16 » fonctionne déjà</span>
                  </div>

                  {componentRow(
                    'reconnaissance vocale hors-ligne (vosk)',
                    '1,4 Go',
                    voskReady,
                    voskBusy,
                    `TÉLÉCHARGEMENT ${Math.round(vosk?.download_progress || 0)} %`,
                    Math.round(vosk?.download_progress || 0),
                    vosk?.last_error,
                    installVosk
                  )}

                  {componentRow(
                    'intelligence sémantique (e5, paraphrases)',
                    '118 Mo',
                    semReady,
                    semBusy,
                    sem?.downloading
                      ? `TÉLÉCHARGEMENT ${Math.round(sem?.download_progress || 0)} %`
                      : `INDEXATION ${sem?.verses_indexed || 0} VERSETS…`,
                    sem?.downloading ? Math.round(sem?.download_progress || 0) : null,
                    sem?.last_error,
                    installSem
                  )}
                </div>
              )}

              {scanned && !backendDown && (
                allReady ? (
                  <p className="fw-ok"><Icon name="check" size={13} /> tout est déjà installé — rien à télécharger.</p>
                ) : anyBusy ? (
                  <p className="fw-hint">
                    téléchargement en cours — vous pouvez continuer, l'installation
                    se poursuit en arrière-plan.
                  </p>
                ) : (
                  <button className="vp-btn vp-btn--primary fw-install-all" onClick={installMissing}>
                    tout installer ({missing.length === 2 ? '1,5 Go' : missing[0] === 'vosk' ? '1,4 Go' : '118 Mo'})
                  </button>
                )
              )}
            </>
          )}

          {STEPS[step] === 'micro' && (
            <>
              <h1 className="fw-title">le micro, maintenant.</h1>
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
                <p className="fw-warn">accès refusé — autorisez le micro dans les réglages système, ou continuez : vous pourrez le faire plus tard.</p>
              )}
              {anyBusy && <p className="fw-hint">les téléchargements continuent : vosk {voskReady ? 'prêt' : `${Math.round(vosk?.download_progress || 0)} %`} · intelligence {semReady ? 'prête' : sem?.downloading ? `${Math.round(sem?.download_progress || 0)} %` : `indexation ${sem?.verses_indexed || 0}`}</p>}
            </>
          )}

          {STEPS[step] === 'pret' && (
            <>
              <h1 className="fw-title">c'est prêt.</h1>
              <ul className="fw-recap">
                <li><Icon name={voskReady ? 'check' : 'alert'} size={13} /> voix hors-ligne {voskReady ? 'installée' : voskBusy ? 'en cours de téléchargement' : 'non installée'}</li>
                <li><Icon name={semReady ? 'check' : 'alert'} size={13} /> intelligence sémantique {semReady ? 'prête' : semBusy ? 'en préparation' : 'non installée'}</li>
                <li><Icon name={micState === 'live' ? 'check' : 'alert'} size={13} /> micro {micState === 'live' ? 'testé' : 'à tester dans la régie'}</li>
              </ul>
              <div className="fw-choice">
                <span className="fw-choice-tag">OPTIONNEL · CLOUD</span>
                <strong>clé deepgram (transcription cloud plus précise)</strong>
                <div className="fw-key-row">
                  <input className="vp-input" type="password" placeholder="dg_… ou sk-or-…" value={cloudKey} onChange={(e) => setCloudKey(e.target.value)} />
                  <button className="vp-btn vp-btn--sm" onClick={saveCloudKey} disabled={!cloudKey.trim()}>ok</button>
                </div>
                {cloudSaved && <span className="fw-ok"><Icon name="check" size={12} /> clé enregistrée</span>}
              </div>
              <p className="fw-hint">tout se règle à nouveau dans <strong>paramètres</strong>, à tout moment.</p>
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
