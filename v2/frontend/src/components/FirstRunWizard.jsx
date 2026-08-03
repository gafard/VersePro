import React, { useEffect, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { Icon } from './ui.jsx'
import { BACKEND_BASE, openExternal } from '../env.js'

/*
 * FirstRunWizard - Séquence d'Onboarding Cinématique WOOW
 * Inspirée d'Originkit, Reactbits et CanvasUI.
 *
 * Étape 1 : CHOIX DU MODE (Radio cards 3D : Hybrid, Offline, Cloud)
 * Étape 2 : INSTALLATION & TÉLÉCHARGEMENT NEMOTRON (Barre de progression live 716 Mo)
 * Étape 3 : TEST MICRO (Égaliseur audio HD réactif)
 * Étape 4 : CLÉ CLOUD DEEPGRAM (Bouton d'aide + lien direct console.deepgram.com)
 */

const STEPS = ['mode', 'installation', 'micro', 'pret']

export default function FirstRunWizard({ onDone }) {
  const { updateSettings } = useStore()
  const [step, setStep] = useState(0)
  const [entered, setEntered] = useState(false)

  // Mode choisi par l'utilisateur : 'hybrid' (recommandé), 'offline', 'cloud'
  const [usageMode, setUsageMode] = useState('hybrid')

  useEffect(() => {
    const t = setTimeout(() => setEntered(true), 40)
    return () => clearTimeout(t)
  }, [])

  // ── Statuts Moteurs (Nemotron + Sémantique) ──
  const [nemo, setNemo] = useState(null)
  const [sem, setSem] = useState(null)
  const [scanned, setScanned] = useState(false)
  const [backendDown, setBackendDown] = useState(false)
  const [downloadStarted, setDownloadStarted] = useState(false)

  const pollStatuses = async () => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 6000)
    try {
      const [nr, sr] = await Promise.all([
        fetch(`${BACKEND_BASE}/api/v1/nemotron/status`, { signal: controller.signal }),
        fetch(`${BACKEND_BASE}/api/v1/semantic/status`, { signal: controller.signal })
      ])
      setNemo(await nr.json())
      setSem(await sr.json())
      setBackendDown(false)
    } catch {
      setBackendDown(true)
    } finally {
      clearTimeout(timeout)
      setScanned(true)
    }
  }

  useEffect(() => {
    pollStatuses()
    const id = setInterval(pollStatuses, 500)
    return () => clearInterval(id)
  }, [])

  const nemoReady = Boolean(nemo?.installed || nemo?.ready)
  const semReady = Boolean(sem?.installed)
  const nemoBusy = Boolean(nemo?.downloading)
  const semBusy = Boolean(sem && (sem.downloading || sem.indexing))

  const nemoPct = nemoReady ? 100 : (nemo?.download_progress ? Math.round(nemo.download_progress * 100) : 0)
  const semPct = semReady ? 100 : (sem?.downloading ? Math.round((sem?.download_progress || 0) * 100)
    : (sem?.indexing && sem?.verses_total ? Math.round((sem.verses_indexed / sem.verses_total) * 100) : 0))

  // Lancement automatique du téléchargement de Nemotron dès le choix du mode
  const triggerInstallation = async () => {
    if (usageMode !== 'cloud' && !nemoReady && !downloadStarted) {
      setDownloadStarted(true)
      try {
        await fetch(`${BACKEND_BASE}/api/v1/nemotron/download`, { method: 'POST' })
        await fetch(`${BACKEND_BASE}/api/v1/semantic/prepare`, { method: 'POST' })
      } catch {
        setBackendDown(true)
      }
    }
    go(1)
  }

  // ── Micro : Visualiseur live HD ──
  const [micState, setMicState] = useState('idle')
  const [bars, setBars] = useState(() => new Array(36).fill(6))
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
      analyser.fftSize = 128
      ctx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      micRefs.current = { stream, ctx, raf: null }

      const tick = () => {
        analyser.getByteFrequencyData(data)
        const next = new Array(36).fill(0).map((_, i) => {
          const v = data[Math.floor(i / 36 * data.length)] || 0
          return 6 + Math.round((v / 255) * 60)
        })
        setBars(next)
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
  const micActive = micState === 'live' && bars.some((b) => b > 18)

  // ── Clé Cloud ──
  const [cloudKey, setCloudKey] = useState('')
  const [cloudSaved, setCloudSaved] = useState(false)

  const saveCloudKey = async () => {
    const key = cloudKey.trim()
    if (!key) return
    const payload = key.startsWith('sk-or-') ? { openrouter_api_key: key } : { deepgram_api_key: key }
    if (await updateSettings(payload)) setCloudSaved(true)
  }

  const go = (nextStep) => {
    setEntered(false)
    setTimeout(() => {
      setStep(nextStep)
      setEntered(true)
    }, 200)
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

  const stepLabel = ['UTILISATION', 'INSTALLATION', 'MICRO', 'PRÊT'][step]

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/90 backdrop-blur-3xl transition-opacity duration-300">
      
      {/* Rayons lumineux 3D d'ambiance (Originkit style) */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-48 -left-48 w-[500px] h-[500px] bg-sky-500/20 rounded-full blur-[140px] animate-pulse" style={{ animationDuration: '6s' }} />
        <div className="absolute -bottom-48 -right-48 w-[500px] h-[500px] bg-indigo-500/20 rounded-full blur-[140px] animate-pulse" style={{ animationDuration: '8s' }} />
      </div>

      {/* Main 3D Card Panel (CanvasUI / Reactbits Glassmorphism) */}
      <div className={`relative w-full max-w-2xl bg-slate-900/85 border border-white/15 shadow-[0_0_80px_rgba(0,0,0,0.9)] rounded-3xl overflow-hidden transition-all duration-300 ease-out transform ${
        entered ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-3'
      }`}>
        
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/30 flex items-center justify-center p-1.5 shadow-[0_0_15px_rgba(56,189,248,0.3)]">
              <img src="/icons/icon-192.png" alt="VersePro" className="w-full h-full object-contain" />
            </div>
            <div>
              <div className="font-bold text-white tracking-wide text-sm flex items-center gap-2">
                VersePro <span className="text-[10px] font-mono uppercase bg-sky-500/20 text-sky-300 px-2 py-0.5 rounded-md border border-sky-500/30">V2.0</span>
              </div>
              <div className="text-[11px] text-slate-400">Assistant de Configuration de Régie</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono tracking-wider text-sky-300 uppercase bg-sky-950/80 px-3 py-1 rounded-full border border-sky-500/30 shadow-inner">
              Étape 0{step + 1} · {stepLabel}
            </span>
          </div>
        </header>

        {/* Step Progress Bar */}
        <div className="w-full bg-slate-950/60 h-1.5">
          <div
            className="h-full bg-gradient-to-r from-sky-500 via-indigo-400 to-emerald-400 transition-all duration-500 ease-out shadow-[0_0_15px_rgba(56,189,248,0.9)]"
            style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
          />
        </div>

        {/* Card Body */}
        <main className="p-8 min-h-[420px] flex flex-col justify-center">

          {/* ───────── ÉTAPE 01 : CHOIX DU MODE D'UTILISATION ───────── */}
          {STEPS[step] === 'mode' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              <div className="text-center space-y-2">
                <h1 className="text-2xl font-bold tracking-tight text-white">Comment souhaitez-vous utiliser VersePro ?</h1>
                <p className="text-sm text-slate-400">Sélectionnez le mode d'exploitation adapté à votre équipement d'église.</p>
              </div>

              {/* 3D Radio Cards Selection (Originkit style) */}
              <div className="space-y-3 pt-2">

                {/* Mode Hybride Recommandé */}
                <div
                  onClick={() => setUsageMode('hybrid')}
                  className={`relative p-4 rounded-2xl border cursor-pointer transition-all duration-200 ${
                    usageMode === 'hybrid'
                      ? 'bg-gradient-to-r from-sky-950/60 to-slate-900 border-sky-500/60 shadow-[0_0_30px_rgba(56,189,248,0.25)] scale-[1.01]'
                      : 'bg-slate-900/40 border-white/5 hover:border-white/20 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    <div className={`mt-0.5 w-5 h-5 rounded-full border flex items-center justify-center ${
                      usageMode === 'hybrid' ? 'border-sky-400 bg-sky-500/20 text-sky-400' : 'border-slate-600'
                    }`}>
                      {usageMode === 'hybrid' && <div className="w-2.5 h-2.5 rounded-full bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.9)]" />}
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-white flex items-center gap-2">
                          Mode Recommandé <span className="text-[10px] uppercase font-mono bg-sky-500/20 text-sky-300 px-2 py-0.5 rounded border border-sky-500/30">Cloud + Hors-ligne</span>
                        </span>
                        <span className="text-xs font-semibold text-emerald-400">Option idéale</span>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Reconnaissance vocale ultra-rapide Deepgram Cloud quand Internet est présent,
                        avec secours automatique local <strong>NVIDIA Nemotron 3.5-ASR (716 Mo)</strong>.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Mode Hors-ligne Uniquement */}
                <div
                  onClick={() => setUsageMode('offline')}
                  className={`relative p-4 rounded-2xl border cursor-pointer transition-all duration-200 ${
                    usageMode === 'offline'
                      ? 'bg-gradient-to-r from-emerald-950/60 to-slate-900 border-emerald-500/60 shadow-[0_0_30px_rgba(52,211,153,0.25)] scale-[1.01]'
                      : 'bg-slate-900/40 border-white/5 hover:border-white/20 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    <div className={`mt-0.5 w-5 h-5 rounded-full border flex items-center justify-center ${
                      usageMode === 'offline' ? 'border-emerald-400 bg-emerald-500/20 text-emerald-400' : 'border-slate-600'
                    }`}>
                      {usageMode === 'offline' && <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]" />}
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-white flex items-center gap-2">
                          Hors-ligne uniquement
                          <span className="text-[10px] uppercase font-mono bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/30">100% Autonome</span>
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Zéro dépendance Internet le dimanche. Exécute Nemotron 3.5-ASR 0.6B en local via l'accélération GPU Metal/CUDA (31x temps réel).
                      </p>
                    </div>
                  </div>
                </div>

                {/* Mode Cloud Uniquement */}
                <div
                  onClick={() => setUsageMode('cloud')}
                  className={`relative p-4 rounded-2xl border cursor-pointer transition-all duration-200 ${
                    usageMode === 'cloud'
                      ? 'bg-gradient-to-r from-indigo-950/60 to-slate-900 border-indigo-500/60 shadow-[0_0_30px_rgba(129,140,248,0.25)] scale-[1.01]'
                      : 'bg-slate-900/40 border-white/5 hover:border-white/20 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    <div className={`mt-0.5 w-5 h-5 rounded-full border flex items-center justify-center ${
                      usageMode === 'cloud' ? 'border-indigo-400 bg-indigo-500/20 text-indigo-400' : 'border-slate-600'
                    }`}>
                      {usageMode === 'cloud' && <div className="w-2.5 h-2.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.9)]" />}
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-white">Cloud uniquement</span>
                        <span className="text-xs text-slate-500">Clé Deepgram requise</span>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Utilise uniquement l'API Cloud Deepgram. Aucun modèle local téléchargé. Connexion Internet permanente obligatoire pendant le culte.
                      </p>
                    </div>
                  </div>
                </div>

              </div>

              {/* Action Button */}
              <div className="text-center pt-2">
                <button
                  className="px-8 py-3 rounded-2xl bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-400 text-slate-950 font-bold text-sm shadow-[0_0_30px_rgba(56,189,248,0.4)] hover:shadow-[0_0_45px_rgba(56,189,248,0.7)] transition-all hover:scale-[1.02] active:scale-[0.98]"
                  onClick={triggerInstallation}
                >
                  Valider et Continuer →
                </button>
              </div>
            </div>
          )}

          {/* ───────── ÉTAPE 02 : INSTALLATION & PRÉPARATION EN DIRECT ───────── */}
          {STEPS[step] === 'installation' && (
            <div className="space-y-6 animate-in fade-in duration-300 text-center">
              <div className="space-y-2">
                <h1 className="text-2xl font-bold tracking-tight text-white">Préparation de votre Régie</h1>
                <p className="text-sm text-slate-400">
                  {usageMode === 'cloud'
                    ? 'Configuration des accès Cloud et des index de Bible.'
                    : 'Téléchargement et préparation de l\'ASR local Nemotron 3.5-ASR (716 Mo).'}
                </p>
              </div>

              {/* Installation Progress Card Géante */}
              <div className="w-full max-w-lg mx-auto p-6 rounded-3xl bg-slate-950/90 border border-emerald-500/30 text-left space-y-5 shadow-[0_0_50px_rgba(16,185,129,0.15)] backdrop-blur-xl">
                
                {/* Header Carte */}
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <span className="text-xs uppercase tracking-wider font-mono text-emerald-400 font-bold flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    Moteur IA & Base de Données
                  </span>
                  <span className="text-[11px] font-mono text-slate-400">VersePro v2.0</span>
                </div>

                {/* 1. Bibles */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3 text-white">
                    <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold border border-emerald-500/30">✓</div>
                    <span className="font-medium">Bibles Intégrées (LSG 1910, KJF, Semeur, TOB)</span>
                  </div>
                  <span className="font-mono text-emerald-400 font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">Prêt</span>
                </div>

                {/* 2. Moteur NDI */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3 text-white">
                    <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold border border-emerald-500/30">✓</div>
                    <span className="font-medium">Sorties Moteur NDI & ProPresenter API</span>
                  </div>
                  <span className="font-mono text-emerald-400 font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">Prêt</span>
                </div>

                {/* 3. Nemotron 3.5 ASR Download MASSIVE CARD */}
                {usageMode !== 'cloud' && (
                  <div className="space-y-3 pt-3 border-t border-white/10 bg-slate-900/60 p-4 rounded-2xl border border-sky-500/30">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-3 text-white font-bold">
                        <div className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${
                          nemoReady ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-sky-500/20 text-sky-400 border border-sky-500/40 animate-pulse'
                        }`}>
                          {nemoReady ? '✓' : '↓'}
                        </div>
                        <div className="flex flex-col">
                          <span>NVIDIA Nemotron 3.5-ASR (0.6B)</span>
                          <span className="text-[11px] font-normal text-slate-400">
                            {nemoReady ? 'Modèle local prêt pour streaming GPU' : nemoBusy ? 'Téléchargement direct Hugging Face...' : 'Préparation du modèle local (716 Mo)...'}
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="font-mono text-base text-sky-400 font-black tracking-tight">{nemoReady ? '100%' : `${nemoPct}%`}</span>
                        <div className="text-[10px] font-mono text-slate-400">{nemoReady ? '716 / 716 Mo' : `${Math.round((nemoPct / 100) * 716)} / 716 Mo`}</div>
                      </div>
                    </div>

                    {/* Progress Bar Géante */}
                    <div className="w-full bg-slate-950 h-3 rounded-full overflow-hidden p-0.5 border border-sky-500/20 shadow-inner">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-sky-500 via-indigo-400 to-emerald-400 transition-all duration-300 shadow-[0_0_15px_rgba(56,189,248,0.9)]"
                        style={{ width: `${Math.max(4, nemoPct)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Vous pouvez continuer la configuration — le téléchargement se poursuit de manière transparente en arrière-plan.
              </p>

              <div className="pt-2">
                <button
                  className="px-6 py-2.5 rounded-xl bg-sky-500 text-slate-950 font-bold text-sm hover:bg-sky-400 transition-all hover:scale-[1.02] active:scale-[0.98]"
                  onClick={() => go(2)}
                >
                  Continuer vers le Micro →
                </button>
              </div>
            </div>
          )}

          {/* ───────── ÉTAPE 03 : TEST MICRO ───────── */}
          {STEPS[step] === 'micro' && (
            <div className="flex flex-col items-center text-center space-y-6 animate-in fade-in duration-300">
              <div className="space-y-2">
                <h1 className="text-2xl font-bold tracking-tight text-white">Test du Microphone de Régie</h1>
                <p className="text-sm text-slate-400">Autorisez l'accès audio et parlez : l'égaliseur doit réagir en temps réel.</p>
              </div>

              {/* Equalizer Visualizer (Reactbits style) */}
              <div className={`w-full max-w-md h-32 rounded-2xl bg-slate-950/90 border p-4 flex items-center justify-center gap-1.5 transition-all shadow-2xl ${
                micActive
                  ? 'border-emerald-500/60 shadow-[0_0_40px_rgba(52,211,153,0.25)]'
                  : micState === 'live'
                  ? 'border-sky-500/40'
                  : 'border-white/10'
              }`}>
                {bars.map((h, i) => (
                  <span
                    key={i}
                    className={`w-2.5 rounded-full transition-all duration-75 ${
                      micActive
                        ? 'bg-gradient-to-t from-emerald-500 via-sky-400 to-indigo-400 shadow-[0_0_10px_rgba(52,211,153,0.8)]'
                        : micState === 'live'
                        ? 'bg-sky-500/40'
                        : 'bg-slate-800'
                    }`}
                    style={{ height: `${micState === 'live' ? h : 8}px` }}
                  />
                ))}
              </div>

              {/* Status Indicator */}
              {micState === 'live' ? (
                <div className={`flex items-center gap-2 px-4 py-2 rounded-full border text-xs font-medium ${
                  micActive
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-slate-800 border-white/10 text-slate-400'
                }`}>
                  <Icon name="check" size={14} />
                  {micActive ? 'Signal audio reçu — micro de régie opérationnel' : 'Parlez pour voir l\'égaliseur réagir'}
                </div>
              ) : (
                <button
                  className="px-6 py-2.5 rounded-xl bg-sky-500 text-slate-950 font-bold text-sm hover:bg-sky-400 transition-all hover:scale-[1.02] active:scale-[0.98]"
                  onClick={startMicTest}
                  disabled={micState === 'asking'}
                >
                  {micState === 'asking' ? 'Autorisation en cours…' : 'Activer le Micro'}
                </button>
              )}

              {micState === 'denied' && (
                <p className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 px-4 py-2 rounded-xl">
                  Accès refusé — vous pourrez réautoriser le micro dans les Réglages Système à tout moment.
                </p>
              )}
            </div>
          )}

          {/* ───────── ÉTAPE 04 : PRÊT & CLÉ CLOUD ───────── */}
          {STEPS[step] === 'pret' && (
            <div className="flex flex-col items-center text-center space-y-6 animate-in fade-in duration-300">
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shadow-[0_0_40px_rgba(52,211,153,0.3)]">
                <Icon name="check" size={36} />
              </div>

              <div className="space-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-white">Votre Régie VersePro est Prête</h1>
                <p className="text-sm text-slate-400">Tout est configuré pour vos projections et diffusions en direct.</p>
              </div>

              {/* Deepgram Key card with Help Link */}
              <div className="w-full max-w-md p-5 rounded-2xl bg-slate-950/90 border border-white/10 text-left space-y-3 shadow-2xl">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider bg-sky-500/20 text-sky-300 px-2 py-0.5 rounded border border-sky-500/30">Clé Cloud Optionnelle</span>
                  <button
                    onClick={() => openExternal('https://console.deepgram.com')}
                    className="text-[11px] text-sky-400 hover:text-sky-300 underline font-medium"
                  >
                    Obtenir une clé gratuite ↗
                  </button>
                </div>
                <div className="text-xs font-semibold text-white">Clé API Deepgram (Transcription Cloud &lt; 0.3s)</div>
                <div className="flex gap-2">
                  <input
                    type="password"
                    placeholder="dg_…"
                    value={cloudKey}
                    onChange={(e) => setCloudKey(e.target.value)}
                    className="flex-1 px-3.5 py-2 rounded-xl bg-slate-900 border border-white/10 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-sky-500"
                  />
                  <button
                    onClick={saveCloudKey}
                    disabled={!cloudKey.trim()}
                    className="px-4 py-2 rounded-xl bg-sky-500 text-slate-950 font-bold text-xs disabled:opacity-50 hover:bg-sky-400 transition-all"
                  >
                    Enregistrer
                  </button>
                </div>
                {cloudSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><Icon name="check" size={14} /> Clé enregistrée avec succès</span>}
              </div>
            </div>
          )}

        </main>

        {/* Footer Navigation */}
        <footer className="flex items-center justify-between px-6 py-4 border-t border-white/10 bg-slate-900/60">
          <button className="text-xs text-slate-400 hover:text-white transition-colors" onClick={finish}>
            Passer
          </button>

          <div className="flex items-center gap-3">
            {step > 0 && (
              <button
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-medium border border-white/10 hover:bg-slate-700 transition-all"
                onClick={() => go(step - 1)}
              >
                Retour
              </button>
            )}

            {step < STEPS.length - 1 ? (
              <button
                className="px-5 py-2 rounded-xl bg-sky-500 text-slate-950 text-xs font-bold hover:bg-sky-400 shadow-md transition-all hover:scale-[1.02] active:scale-[0.98]"
                onClick={() => (step === 0 ? triggerInstallation() : go(step + 1))}
              >
                Continuer →
              </button>
            ) : (
              <button
                className="px-6 py-2 rounded-xl bg-gradient-to-r from-emerald-400 to-sky-500 text-slate-950 text-xs font-bold hover:shadow-[0_0_30px_rgba(52,211,153,0.6)] transition-all hover:scale-[1.02] active:scale-[0.98]"
                onClick={finish}
              >
                Ouvrir la Régie VersePro →
              </button>
            )}
          </div>
        </footer>

      </div>
    </div>
  )
}
