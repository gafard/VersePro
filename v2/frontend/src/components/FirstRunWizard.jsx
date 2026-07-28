import React, { useEffect, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'
import { BACKEND_BASE } from '../env.js'

/*
 * Premier lancement — séquence cinématique « préparation de la régie ».
 * Trois temps : PRÉPARATION (scan sonar du poste + installation des composants
 * IA avec anneaux de progression), MICRO (visualiseur d'onde live), PRÊT
 * (révélation finale + clé cloud). Toute la logique fonctionnelle (statuts,
 * téléchargements, test micro) est conservée ; c'est l'enveloppe qui devient
 * vivante. Design : palette Lumen Night Foundry, display Space Grotesk.
 */

const STEPS = ['preparation', 'micro', 'pret']

// ── Anneau de progression circulaire (SVG) ──
function Ring({ pct, size = 128, stroke = 6, state = 'idle', big }) {
  const r = (size - stroke * 2) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, pct || 0))
  const off = c * (1 - clamped / 100)
  return (
    <div className={`fw-ring fw-ring--${state}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="fw-ring-track" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none" />
        <circle
          className="fw-ring-fill" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={state === 'done' ? 0 : off}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="fw-ring-core">
        {state === 'done'
          ? <Icon name="check" size={big ? 30 : 22} />
          : <span className="fw-ring-pct">{Math.round(clamped)}<i>%</i></span>}
      </div>
    </div>
  )
}

export default function FirstRunWizard({ onDone }) {
  const { updateSettings } = useStore()
  const [step, setStep] = useState(0)
  const [entered, setEntered] = useState(false)
  useEffect(() => { const t = setTimeout(() => setEntered(true), 40); return () => clearTimeout(t) }, [])

  // ── Statuts Vosk + sémantique (scan continu) ──
  // ── Ouverture cinématique ──
  // La séquence se joue TOUJOURS, même quand les moteurs sont déjà installés.
  // Sans cela un poste déjà équipé ouvrait l'assistant sur son image finale :
  // anneau coché, trois lignes vertes, plus rien en mouvement. L'opérateur ne
  // voyait pas ce qui avait été vérifié — il voyait un écran mort.
  const REVEAL_AT_MS = [1450, 1720, 1990]
  const SETTLE_AT_MS = 2320
  const [revealed, setRevealed] = useState(0)
  const [settled, setSettled] = useState(false)
  const reducedMotion = useRef(
    typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  ).current
  useEffect(() => {
    if (reducedMotion) { setRevealed(3); setSettled(true); return }
    const timers = REVEAL_AT_MS.map((ms, i) => setTimeout(() => setRevealed(i + 1), ms))
    timers.push(setTimeout(() => setSettled(true), SETTLE_AT_MS))
    return () => timers.forEach(clearTimeout)
  }, [])

  const [vosk, setVosk] = useState(null)
  const [sem, setSem] = useState(null)
  const [scanned, setScanned] = useState(false)
  const [backendDown, setBackendDown] = useState(false)
  const downSinceRef = useRef(null)
  const [launched, setLaunched] = useState(false)
  const autoAdvanced = useRef(false)

  const pollStatuses = async () => {
    // Sans délai, une requête émise pendant que le moteur charge ses index peut
    // rester suspendue et figer le sondage. On abandonne au bout de 8 s : la
    // tentative suivante (toutes les 1,5 s) reprendra la main.
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8000)
    try {
      const [vr, sr] = await Promise.all([
        fetch(`${BACKEND_BASE}/api/v1/vosk/status`, { signal: controller.signal }),
        fetch(`${BACKEND_BASE}/api/v1/semantic/status`, { signal: controller.signal })
      ])
      setVosk(await vr.json()); setSem(await sr.json())
      setBackendDown(false); downSinceRef.current = null
    } catch {
      setBackendDown(true)
      if (downSinceRef.current === null) downSinceRef.current = Date.now()
    } finally { clearTimeout(timeout); setScanned(true) }
  }
  useEffect(() => { pollStatuses(); const id = setInterval(pollStatuses, 1500); return () => clearInterval(id) }, [])

  // Passé un délai généreux, « patientez » devient un mensonge : un moteur qui
  // n'a pas répondu en 45 s ne charge plus ses index, il ne démarre pas. Un
  // poste d'église a connu ce cas — installation faite par-dessus une version
  // en cours d'exécution, bibliothèque sautée, moteur incapable de vivre.
  const [tropLong, setTropLong] = useState(false)
  useEffect(() => {
    if (!backendDown) { setTropLong(false); return }
    const id = setInterval(() => {
      const depuis = downSinceRef.current
      if (depuis && Date.now() - depuis > 45000) setTropLong(true)
    }, 2000)
    return () => clearInterval(id)
  }, [backendDown])

  const voskReady = Boolean(vosk?.installed)
  const semReady = Boolean(sem?.installed)
  const voskBusy = Boolean(vosk?.downloading)
  const semBusy = Boolean(sem && (sem.downloading || sem.indexing))
  const allReady = voskReady && semReady
  const anyBusy = voskBusy || semBusy
  const missing = [!voskReady && 'vosk', !semReady && 'sem'].filter(Boolean)
  // Le grand modèle FR est le choix assumé : au réel, il bat Whisper en
  // justesse comme en réactivité. Son poids n'est payé qu'une seule fois.
  const voskSize = (vosk?.model_name || '').includes('small') ? 45 : 1400
  const fmtSize = (mo) => (mo >= 1000 ? `~${(mo / 1000).toFixed(1).replace('.', ',')} Go` : `~${mo} Mo`)

  const installVosk = async () => {
    try {
      await fetch(`${BACKEND_BASE}/api/v1/vosk/download`, { method: 'POST' })
    } catch { setBackendDown(true) }
  }
  const installSem = async () => { try { await fetch(`${BACKEND_BASE}/api/v1/semantic/prepare`, { method: 'POST' }) } catch { setBackendDown(true) } }
  const installMissing = async () => {
    setLaunched(true)
    await Promise.all([!voskReady && installVosk(), !semReady && installSem()].filter(Boolean))
    pollStatuses()
  }
  useEffect(() => {
    if (launched && allReady && !autoAdvanced.current && STEPS[step] === 'preparation') {
      autoAdvanced.current = true
      const t = setTimeout(() => go(1), 1600); return () => clearTimeout(t)
    }
  }, [launched, allReady, step])

  // ── Progression fusionnée (pour l'anneau maître) ──
  const voskPct = voskReady ? 100 : (vosk?.downloading ? (vosk?.download_progress || 0) : 0)
  const semPct = semReady ? 100 : (sem?.downloading ? (sem?.download_progress || 0)
    : (sem?.indexing && sem?.verses_total ? (sem.verses_indexed / sem.verses_total) * 100 : 0))
  const totalPct = Math.round((voskPct + semPct + 100) / 3) // +100 = index lexical inclus

  // ── Micro : visualiseur live ──
  const [micState, setMicState] = useState('idle')
  const [bars, setBars] = useState(() => new Array(28).fill(6))
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
      const analyser = ctx.createAnalyser(); analyser.fftSize = 64
      ctx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      micRefs.current = { stream, ctx, raf: null }
      const tick = () => {
        analyser.getByteFrequencyData(data)
        const next = new Array(28).fill(0).map((_, i) => {
          const v = data[Math.floor(i / 28 * data.length)] || 0
          return 6 + Math.round((v / 255) * 46)
        })
        setBars(next)
        micRefs.current.raf = requestAnimationFrame(tick)
      }
      tick(); setMicState('live')
    } catch { setMicState('denied') }
  }
  useEffect(() => () => stopMicTest(), [])
  useEffect(() => { if (STEPS[step] !== 'micro') stopMicTest() }, [step])
  const micActive = micState === 'live' && bars.some((b) => b > 14)

  // ── Clé cloud ──
  const [cloudKey, setCloudKey] = useState('')
  const [cloudSaved, setCloudSaved] = useState(false)
  const saveCloudKey = async () => {
    const key = cloudKey.trim(); if (!key) return
    const payload = key.startsWith('sk-or-') ? { openrouter_api_key: key } : { deepgram_api_key: key }
    if (await updateSettings(payload)) setCloudSaved(true)
  }

  const go = (i) => { setEntered(false); setTimeout(() => { setStep(i); setEntered(true) }, 260) }
  const finish = () => {
    stopMicTest()
    try {
      localStorage.setItem('versepro_first_run_done', 'true')
      localStorage.setItem('versepro_onboarding_ignored', 'true')
      localStorage.setItem('versepro_last_tab', 'live')
    } catch { /* stockage privé */ }
    onDone()
  }

  const stepLabel = ['PRÉPARATION', 'MICRO', 'PRÊT'][step]

  // L'étape 01 porte déjà son action dans le corps — préparation des moteurs,
  // « réessayer », ou « continuer → ». Le bouton du pied ferait doublon, sauf
  // pendant un téléchargement, où le corps n'affiche rien et où l'on doit
  // pouvoir avancer quand même.
  const ctaDansLeCorps = step === 0 && settled && scanned && !backendDown && !anyBusy

  return (
    <div className="fw-backdrop" role="dialog" aria-modal="true" aria-label="Premier lancement">
      <div className={`fw-panel ${entered ? 'is-in' : ''}`}>
        <header className="fw-head">
          <span className="fw-brand flex items-center gap-2">
            <img src="/icons/icon-192.png" alt="VersePro" className="w-5 h-5 rounded object-contain" />
            <span>versepro</span>
          </span>
          <span className="fw-step-label">{`0${step + 1} · ${stepLabel}`}</span>
        </header>
        <div className="fw-progress" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s} className={i <= step ? 'is-done' : ''} />)}
        </div>

        <main className="fw-body">
          {/* ───────── PRÉPARATION ───────── */}
          {STEPS[step] === 'preparation' && (
            <div className="fw-prep">
              <div className="fw-prep-stage">
                {!settled && (
                  <div className="fw-sonar" aria-hidden="true">
                    <span /><span /><span /><i><Icon name="mic" size={26} /></i>
                  </div>
                )}
                {settled && (anyBusy || launched || allReady) && (
                  <Ring pct={totalPct} size={168} stroke={7} big state={allReady ? 'done' : 'busy'} />
                )}
                {settled && !allReady && !anyBusy && !launched && (
                  <div className="fw-prep-count"><strong>{missing.length === 0 ? 3 : 3 - missing.length}</strong><span>/ 3 prêts</span></div>
                )}
              </div>

              <h1 className="fw-title">
                {!settled ? 'analyse de votre poste…'
                  : allReady ? 'votre régie est parée.'
                  : anyBusy ? 'installation en cours…'
                  : 'préparons votre régie.'}
              </h1>
              <p className="fw-lede">
                {!settled ? 'versepro inventorie ce qui est déjà là et ce qu\'il reste à installer.'
                  : allReady ? 'tous les moteurs sont là. on passe au micro.'
                  : anyBusy ? 'vous pouvez continuer — le téléchargement se poursuit en arrière-plan.'
                  : 'versepro analyse votre poste et télécharge ce qu\'il faut pour fonctionner sans internet le dimanche.'}
              </p>

              {backendDown && !tropLong && (
                // Dans l'application empaquetée le moteur démarre seul, mais il
                // charge d'abord ses index (~10 s sur un PC modeste) : dire
                // « lancez le backend » n'aidait personne, c'était impossible à faire.
                <p className="fw-warn">le moteur démarre encore — il charge la Bible et ses index. patientez quelques secondes, puis{' '}
                  <button className="vp-btn vp-btn--sm" onClick={pollStatuses}>réessayer</button></p>
              )}
              {backendDown && tropLong && (
                <p className="fw-warn">le moteur ne démarre pas. l'installation est probablement incomplète —
                  cela arrive quand VersePro tournait encore pendant sa propre mise à jour.
                  <br />réinstallez après avoir fermé VersePro, puis supprimé le dossier
                  {' '}<span className="mono">VersePro</span> dans <span className="mono">%LOCALAPPDATA%</span>.
                  {' '}<button className="vp-btn vp-btn--sm" onClick={pollStatuses}>réessayer</button></p>
              )}

              {scanned && !backendDown && (
                <ul className="fw-comps">
                  {revealed > 0 && (
                  <li className="fw-comp fw-comp--in is-ready">
                    <Icon name="check" size={15} />
                    <div><strong>index lexical des citations</strong><small>inclus · « jean 3 verset 16 » fonctionne déjà</small></div>
                    <span className="fw-comp-size">0 Mo</span>
                  </li>
                  )}
                  {revealed > 1 && (
                  <li className={`fw-comp fw-comp--in ${voskReady ? 'is-ready' : voskBusy ? 'is-busy' : ''}`}>
                    {voskReady ? <Icon name="check" size={15} /> : voskBusy ? <span className="fw-mini-pct">{Math.round(voskPct)}%</span> : <span className="fw-dot" />}
                    <div><strong>reconnaissance vocale hors-ligne</strong>
                      <small>{vosk?.last_error ? vosk.last_error : voskReady ? 'Vosk français grand modèle prêt' : voskBusy ? (vosk?.download_status === 'extraction' ? 'extraction du modèle…' : `téléchargement de Vosk… ${Math.round(voskPct)}%`) : 'Vosk français grand modèle — à télécharger'}</small></div>
                    <span className="fw-comp-size">{fmtSize(voskSize)}</span>
                  </li>
                  )}
                  {revealed > 2 && (
                  <li className={`fw-comp fw-comp--in ${semReady ? 'is-ready' : semBusy ? 'is-busy' : ''}`}>
                    {semReady ? <Icon name="check" size={15} /> : semBusy ? <span className="fw-mini-pct">{Math.round(semPct)}%</span> : <span className="fw-dot" />}
                    <div><strong>intelligence sémantique (paraphrases)</strong>
                      <small>{sem?.last_error ? sem.last_error : semReady ? 'prête' : sem?.downloading ? 'téléchargement…' : sem?.indexing ? `indexation ${sem?.verses_indexed || 0} versets…` : 'e5-base — à installer'}</small></div>
                    <span className="fw-comp-size">265 Mo</span>
                  </li>
                  )}
                </ul>
              )}

              {settled && scanned && !backendDown && (
                allReady
                  ? <button className="vp-btn vp-btn--primary fw-cta" onClick={() => go(1)}>continuer →</button>
                  : anyBusy
                    ? null
                    : (vosk?.last_error || sem?.last_error)
                      ? <button className="vp-btn vp-btn--primary fw-cta" onClick={installMissing}>réessayer l'installation</button>
                      : <button className="vp-btn vp-btn--primary fw-cta" onClick={installMissing}>
                          tout préparer ({missing.length === 2 ? fmtSize(voskSize + 265) : missing[0] === 'vosk' ? fmtSize(voskSize) : '~265 Mo'})
                        </button>
              )}
            </div>
          )}

          {/* ───────── MICRO ───────── */}
          {STEPS[step] === 'micro' && (
            <div className="fw-mic">
              <h1 className="fw-title">le micro, maintenant.</h1>
              <p className="fw-lede">autorisez l'accès et parlez : l'onde doit danser.</p>
              <div className={`fw-wave ${micState === 'live' ? 'is-live' : ''} ${micActive ? 'is-hot' : ''}`}>
                {bars.map((h, i) => <span key={i} style={{ height: `${micState === 'live' ? h : 6}px` }} />)}
              </div>
              {micState !== 'live' ? (
                <button className="vp-btn vp-btn--primary fw-cta" onClick={startMicTest} disabled={micState === 'asking'}>
                  {micState === 'asking' ? 'demande en cours…' : 'tester le micro'}
                </button>
              ) : (
                <p className={`fw-ok ${micActive ? 'is-hot' : ''}`}>
                  <Icon name="check" size={14} /> {micActive ? 'signal reçu — micro opérationnel' : 'parlez pour voir l\'onde réagir'}
                </p>
              )}
              {micState === 'denied' && <p className="fw-warn">accès refusé — autorisez le micro dans les réglages système, ou continuez : vous pourrez le faire plus tard.</p>}
              {anyBusy && <p className="fw-hint">préparation en arrière-plan : Vosk {voskReady ? 'prêt' : `${Math.round(voskPct)}%`} · intelligence {semReady ? 'prête' : `${Math.round(semPct)}%`}</p>}
            </div>
          )}

          {/* ───────── PRÊT ───────── */}
          {STEPS[step] === 'pret' && (
            <div className="fw-done">
              <div className="fw-done-seal"><Icon name="check" size={34} /></div>
              <h1 className="fw-title">c'est prêt.</h1>
              <ul className="fw-recap">
                <li className={voskReady ? 'ok' : ''}><Icon name={voskReady ? 'check' : 'alert'} size={14} /> voix hors-ligne {voskReady ? 'Vosk grand modèle prêt' : voskBusy ? 'en téléchargement' : 'non préparée'}</li>
                <li className={semReady ? 'ok' : ''}><Icon name={semReady ? 'check' : 'alert'} size={14} /> intelligence sémantique {semReady ? 'prête' : semBusy ? 'en préparation' : 'non installée'}</li>
                <li className={micState === 'live' ? 'ok' : ''}><Icon name={micState === 'live' ? 'check' : 'alert'} size={14} /> micro {micState === 'live' ? 'testé' : 'à tester dans la régie'}</li>
              </ul>
              <div className="fw-keycard">
                <span className="fw-choice-tag">OPTIONNEL · CLOUD</span>
                <strong>clé deepgram — transcription cloud plus précise</strong>
                <div className="fw-key-row">
                  <input className="vp-input" type="password" placeholder="dg_… ou sk-or-…" value={cloudKey} onChange={(e) => setCloudKey(e.target.value)} />
                  <button className="vp-btn vp-btn--sm" onClick={saveCloudKey} disabled={!cloudKey.trim()}>ok</button>
                </div>
                {cloudSaved && <span className="fw-ok"><Icon name="check" size={12} /> clé enregistrée</span>}
              </div>
              <p className="fw-hint">tout se règle à nouveau dans <strong>paramètres</strong>, à tout moment.</p>
            </div>
          )}
        </main>

        <footer className="fw-foot">
          <button className="vp-btn vp-btn--ghost" onClick={finish}>passer</button>
          <div className="fw-foot-right">
            {step > 0 && <button className="vp-btn" onClick={() => go(step - 1)}>retour</button>}
            {step < STEPS.length - 1
              ? (!ctaDansLeCorps && <button className="vp-btn vp-btn--primary" onClick={() => go(step + 1)}>continuer</button>)
              : <button className="vp-btn vp-btn--primary" onClick={finish}>ouvrir la régie</button>}
          </div>
        </footer>
      </div>
    </div>
  )
}
