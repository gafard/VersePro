import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useStore } from '../store.js'
import TranscriptTicker from './TranscriptTicker.jsx'
import { BACKEND_BASE, BACKEND_WS_BASE, openExternal } from '../env.js'

const BIBLE_NAMES = {
  LSG: 'Louis Segond 1910',
  SEM: 'La Bible du Semeur',
  KJF: 'King James Française',
  NBS: 'Nouvelle Bible Segond',
  FC: 'Français Courant',
  TOB: 'Traduction Œcuménique (TOB)'
}

const QUICK_REFS = [
  { ref: 'Jean 3:16', label: 'Jn 3:16' },
  { ref: 'Psaume 23:1', label: 'Ps 23:1' },
  { ref: 'Romains 8:28', label: 'Rm 8:28' },
  { ref: 'Éphésiens 2:8', label: 'Éph 2:8' }
]

const ASR_LABELS = {
  deepgram: 'Deepgram cloud',
  vosk: 'Vosk local',
  whisper: 'Whisper local'
}

/** Décale le numéro de verset d'une référence "Livre C:V" (navigation de lecture) */
function shiftVerse(reference, delta) {
  const match = /^(.+?)\s+(\d+):(\d+)/.exec(reference || '')
  if (!match) return null
  const verse = parseInt(match[3], 10) + delta
  if (verse < 1) return null
  return `${match[1]} ${match[2]}:${verse}`
}

function MicIcon({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  )
}

function StopIcon({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <rect x="5" y="5" width="14" height="14" rx="2" />
    </svg>
  )
}

export default function LiveDetection({ setActiveTab }) {
  const {
    isListening,
    currentTranscript,
    detectedReferences,
    propresenterConnected,
    sendReference, sendAudio,
    asrMode, fetchBibles,
    aiActive,
    translationLang, currentTranslation, setTranslationLang,
    autopilotMode, setAutopilotMode,
    projectionQueue, projectVerseFromQueue, rejectVerseFromQueue, clearProjectionQueue,
    lastAiRejection,
    onAir, clearProjectionScreen,
    statistics,
    toggleListening, volume, waveform, audioDevices, selectedAudioDeviceId, micError, refreshAudioDevices, setMicPermissionState,
    preflight, preflightLoading, runPreflight, activatePanicMode, sundaySafeMode, shadowMode,
    listeningStartedAt, listeningStoppedAt
  } = useStore()

  const [manualReference, setManualReference] = useState('')
  const [selectedQueueIndex, setSelectedQueueIndex] = useState(0)
  const [visibleRejection, setVisibleRejection] = useState(null)
  const [clock, setClock] = useState(() => new Date())
  const [followMode, setFollowMode] = useState(false)
  const [preflightOpen, setPreflightOpen] = useState(false)
  const [projectingIds, setProjectingIds] = useState(new Set())
  const [failedIds, setFailedIds] = useState(new Set())
  const [dismissedPpAlert, setDismissedPpAlert] = useState(() => {
    try { return localStorage.getItem('versepro_dismiss_pp_alert') === 'true' } catch { return false }
  })
  const lastAdvancedRef = useRef(null)

  const manualInputRef = useRef(null)

  // Horloge de régie
  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  // Onde audio réactive du ticker
  useEffect(() => {
    const canvas = document.getElementById('vp-wave')
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    const width = rect.width
    const height = rect.height
    const styles = getComputedStyle(document.documentElement)
    const liveWave = styles.getPropertyValue('--color-wave-live').trim()
    const idleWave = styles.getPropertyValue('--color-wave-idle').trim()

    ctx.clearRect(0, 0, width, height)
    ctx.beginPath()
    ctx.strokeStyle = isListening ? liveWave : idleWave
    ctx.lineWidth = 1.4
    const samples = isListening && waveform?.length ? waveform : [0, 0]
    samples.forEach((sample, index) => {
      const x = (index / Math.max(1, samples.length - 1)) * width
      const y = height / 2 - sample * height * 0.44
      index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
    return () => {
      canvas.width = canvas.width
    }
  }, [isListening, waveform])

  const transcriptEndRef = useRef(null)

  // Auto-scroll de la transcription brute
  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [currentTranscript])

  // Notification de rejet IA (6 s)
  useEffect(() => {
    if (lastAiRejection) {
      setVisibleRejection(lastAiRejection)
      const timer = setTimeout(() => setVisibleRejection(null), 6000)
      return () => clearTimeout(timer)
    }
  }, [lastAiRejection])

  const pendingItems = useMemo(
    () => projectionQueue.filter((item) => item.status === 'pending'),
    [projectionQueue]
  )

  useEffect(() => {
    if (selectedQueueIndex >= pendingItems.length) {
      setSelectedQueueIndex(Math.max(0, pendingItems.length - 1))
    }
  }, [pendingItems, selectedQueueIndex])

  // Raccourcis clavier de régie : ↑/↓ naviguer, Espace/Entrée projeter, Échap ignorer, "/" recherche
  useEffect(() => {
    const handleKeyDown = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)

      if (e.key === '/' && !typing) {
        e.preventDefault()
        manualInputRef.current?.focus()
        return
      }
      if (typing) return
      if (pendingItems.length === 0) return

      const currentItem = pendingItems[selectedQueueIndex]
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedQueueIndex((prev) => Math.min(pendingItems.length - 1, prev + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedQueueIndex((prev) => Math.max(0, prev - 1))
      } else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        if (currentItem) handleProjectFromQueue(currentItem.queueId, currentItem.reference, currentItem.text)
      } else if (e.key === 'Escape' || e.key === 'Backspace') {
        e.preventDefault()
        if (currentItem) rejectVerseFromQueue(currentItem.queueId)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [pendingItems, selectedQueueIndex, projectVerseFromQueue, rejectVerseFromQueue])

  useEffect(() => {
    fetchBibles()
    refreshAudioDevices()
    runPreflight()

    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: 'microphone' })
        .then((permission) => {
          setMicPermissionState(permission.state)
          permission.onchange = () => setMicPermissionState(permission.state)
        })
        .catch(() => {})
    }

    navigator.mediaDevices?.addEventListener?.('devicechange', refreshAudioDevices)
    return () => {
      navigator.mediaDevices?.removeEventListener?.('devicechange', refreshAudioDevices)
    }
  }, [])

  // ── Actions ────────────────────────────────────────────────────
  const handleSendManual = async () => {
    const ref = manualReference.trim()
    if (!ref) return
    await sendReference(ref)
    setManualReference('')
  }

  const handleToggleListening = async () => {
    if (isListening) {
      await toggleListening()
      return
    }
    const result = await runPreflight()
    if (!result.ready) {
      setPreflightOpen(true)
      return
    }
    await toggleListening()
  }

  const handleProjectFromQueue = async (queueId, reference, text) => {
    setProjectingIds((prev) => {
      const next = new Set(prev)
      next.add(queueId)
      return next
    })
    setFailedIds((prev) => {
      const next = new Set(prev)
      next.delete(queueId)
      return next
    })
    try {
      const success = await projectVerseFromQueue(queueId, reference, text)
      if (!success) {
        setFailedIds((prev) => {
          const next = new Set(prev)
          next.add(queueId)
          return next
        })
      }
    } catch (err) {
      console.error('Erreur de projection depuis la file:', err)
      setFailedIds((prev) => {
        const next = new Set(prev)
        next.add(queueId)
        return next
      })
    } finally {
      setProjectingIds((prev) => {
        const next = new Set(prev)
        next.delete(queueId)
        return next
      })
    }
  }

  const handleShiftVerse = async (delta) => {
    const next = shiftVerse(onAir?.reference, delta)
    if (next) await sendReference(next)
  }

  // Les pages d'écran (/output, /stage, /obs) sont servies par le backend
  // FastAPI (port dédié en app, proxy Vite en navigateur). openExternal gère
  // l'ouverture (navigateur système sous Tauri, où window.open est intercepté).
  const openProjectionWindow = () => openExternal(`${BACKEND_BASE}/output`)
  const openObsWindow = () => openExternal(`${BACKEND_BASE}/obs?theme=lower-third&bg=transparent`)
  const openStageWindow = () => openExternal(`${BACKEND_BASE}/stage`)

  // ── Données dérivées ───────────────────────────────────────────
  // ── Lecture vivante côté console : progression AUTORITAIRE du serveur
  // (flux /ws/output, le même que les écrans) avec repli sur l'heuristique locale
  const [serverReading, setServerReading] = useState(null)
  const serverWsUp = useRef(false)
  useEffect(() => {
    let socket = null
    let retryTimer = null
    let closed = false
    const connectOutput = () => {
      const wsBase = BACKEND_WS_BASE || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
      socket = new WebSocket(`${wsBase}/ws/output`)
      socket.onopen = () => { serverWsUp.current = true }
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'reading_progress') {
          setServerReading({ reference: data.reference, matched: data.matched, total: data.total })
        } else if (!data.type || data.type === 'scripture') {
          setServerReading(null) // nouveau verset : progression remise à zéro
        }
      }
      socket.onclose = () => {
        serverWsUp.current = false
        if (!closed) retryTimer = setTimeout(connectOutput, 3000)
      }
    }
    connectOutput()
    return () => {
      closed = true
      clearTimeout(retryTimer)
      if (socket) socket.close()
    }
  }, [])

  // Pastilles rapides : les versets les plus cités de cette église (stats),
  // avec repli sur les classiques tant qu'il n'y a pas d'historique.
  const quickRefs = useMemo(() => {
    const top = (statistics?.top_verses || [])
      .slice(0, 4)
      .map((v) => ({ ref: v.reference, label: v.reference }))
    return top.length >= 2 ? top : QUICK_REFS
  }, [statistics])

  // Plan de culte : lectures préparées à l'avance (persisté localement)
  const [plan, setPlan] = useState(() => {
    try { return JSON.parse(localStorage.getItem('versepro_plan') || '[]') } catch { return [] }
  })
  const [planInput, setPlanInput] = useState('')
  const savePlan = (next) => {
    setPlan(next)
    localStorage.setItem('versepro_plan', JSON.stringify(next))
  }
  const addToPlan = () => {
    const ref = planInput.trim()
    if (!ref) return
    savePlan([...plan, { id: `${Date.now()}`, ref, done: false }])
    setPlanInput('')
  }
  const projectPlanItem = async (item) => {
    await sendReference(item.ref)
    savePlan(plan.map((p) => (p.id === item.id ? { ...p, done: true } : p)))
  }

  // ── Suivi de lecture : mesure la progression du prédicateur dans le verset affiché
  const normalizeWords = (s) => (s || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length >= 3)

  const onAirDisplay = onAir || (() => {
    const projected = projectionQueue.find((item) => item.status === 'projected')
    return projected ? { reference: projected.reference, text: projected.text } : null
  })()

  const followProgress = useMemo(() => {
    if (!followMode || !onAirDisplay?.text) return null
    // 1. Signal serveur (traqueur de lecture, aligné sur les écrans)
    if (serverReading && serverReading.total > 3) {
      return {
        ratio: serverReading.matched / serverReading.total,
        tailReached: serverReading.matched >= serverReading.total - 1
      }
    }
    // 2. Repli local si le flux serveur est indisponible
    if (serverWsUp.current || !currentTranscript) return null
    const verseWords = normalizeWords(onAirDisplay.text)
    if (verseWords.length < 4) return null
    const spoken = new Set(normalizeWords(currentTranscript).slice(-60))
    const covered = verseWords.filter((w) => spoken.has(w)).length
    const tail = verseWords.slice(-5)
    const tailCovered = tail.filter((w) => spoken.has(w)).length
    return {
      ratio: covered / verseWords.length,
      tailReached: tailCovered >= Math.min(4, tail.length)
    }
  }, [followMode, onAirDisplay, currentTranscript, serverReading])

  // Auto-avance : quand la fin du verset est lue, projette le suivant (une seule fois par verset)
  useEffect(() => {
    if (!followMode || !followProgress?.tailReached || !onAirDisplay?.reference) return
    if (lastAdvancedRef.current === onAirDisplay.reference) return
    lastAdvancedRef.current = onAirDisplay.reference
    const timer = setTimeout(() => handleShiftVerse(1), 700)
    return () => clearTimeout(timer)
  }, [followMode, followProgress, onAirDisplay])

  const isSemanticSuggestion = (item) => (
    ['ai', 'semantic'].includes(item.source)
    || ['ai_semantic', 'semantic_local'].includes(item.detectionMethod)
  )
  const pendingLocal = pendingItems.filter((item) => !isSemanticSuggestion(item))
  const pendingAi = pendingItems.filter(isSemanticSuggestion)
  const recentDone = projectionQueue.filter((i) => i.status !== 'pending').slice(0, 3)
  const canShift = Boolean(shiftVerse(onAirDisplay?.reference, 1))
  const selectedAudioDevice = audioDevices.find((device) => device.deviceId === selectedAudioDeviceId)

  const renderCard = (item, accent) => {
    const pendingIdx = pendingItems.findIndex((p) => p.queueId === item.queueId)
    const isKeyboardActive = pendingIdx === selectedQueueIndex
    const confidencePct = item.confidence
      ? Math.round(item.confidence <= 1 ? item.confidence * 100 : item.confidence)
      : null

    const isLoading = projectingIds.has(item.queueId)
    const isFailed = failedIds.has(item.queueId)
    const isProjected = item.status === 'projected'

    return (
      <article
        key={item.queueId}
        className={`live-card ${accent === 'ai' ? 'is-ai' : ''} ${isKeyboardActive ? 'is-keyboard-active' : ''} ${isProjected ? 'is-projected' : ''} ${isLoading ? 'is-loading' : ''} ${isFailed ? 'is-failed' : ''}`}
        onClick={() => setSelectedQueueIndex(pendingIdx)}
      >
        <div className="live-card-head">
          <span className="live-card-ref">{item.reference}</span>
          <span className={`live-card-badge ${accent === 'ai' ? 'is-ai' : 'is-local'} ${isProjected ? 'is-projected-badge' : ''}`}>
            {isProjected ? 'À l\'antenne' : (accent === 'ai' ? `Copilote ${confidencePct ?? 95}%` : 'Direct')}
          </span>
        </div>
        <p className="live-card-text">{item.text || 'Texte non chargé.'}</p>
        <div className="live-card-foot">
          <span className="live-card-time">
            {new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <div className="live-card-actions">
            {!isProjected && (
              <button
                className="vp-btn vp-btn--ghost vp-btn--sm"
                onClick={(e) => { e.stopPropagation(); rejectVerseFromQueue(item.queueId) }}
                disabled={isLoading}
              >
                Ignorer
              </button>
            )}
            
            {isProjected ? (
              <button
                className="vp-btn vp-btn--sm vp-btn--ok"
                disabled
                style={{ cursor: 'default', opacity: 1 }}
              >
                ✓ À l'antenne
              </button>
            ) : isLoading ? (
              <button
                className="vp-btn vp-btn--sm"
                disabled
              >
                Envoi...
              </button>
            ) : isFailed ? (
              <button
                className="vp-btn vp-btn--sm"
                style={{ background: 'var(--danger)', borderColor: 'var(--danger)', color: '#ffffff' }}
                onClick={(e) => { e.stopPropagation(); handleProjectFromQueue(item.queueId, item.reference, item.text) }}
              >
                ⚠ Réessayer
              </button>
            ) : (
              <button
                className={`vp-btn vp-btn--sm ${accent === 'ai' ? 'vp-btn--ai' : 'vp-btn--ok'}`}
                onClick={(e) => { e.stopPropagation(); handleProjectFromQueue(item.queueId, item.reference, item.text) }}
              >
                Projeter
              </button>
            )}
          </div>
        </div>
      </article>
    )
  }

  return (
    <div className="live-shell">
      {preflightOpen && (
        <div className="vp-modal-backdrop">
          <div className="vp-modal preflight-modal" role="dialog" aria-modal="true" aria-label="Contrôle avant direct">
            <div className="settings-card-head">
              <div>
                <span>Avant direct</span>
                <h2>{preflight?.ready ? 'Régie prête' : 'Action requise'}</h2>
              </div>
              <button className="vp-btn vp-btn--ghost vp-btn--sm" onClick={() => setPreflightOpen(false)}>Fermer</button>
            </div>
            <div className="preflight-list">
              {(preflight?.checks || []).map((check) => (
                <div key={check.id} className={`preflight-row ${check.ok ? 'is-ok' : 'is-bad'}`}>
                  <span className="dot" />
                  <strong>{check.label}</strong>
                  <span>{check.detail || (check.ok ? 'Prêt' : check.critical ? 'Bloquant' : 'Optionnel')}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button className="vp-btn" onClick={runPreflight} disabled={preflightLoading}>
                {preflightLoading ? 'Contrôle…' : 'Recontrôler'}
              </button>
              <button className="vp-btn vp-btn--primary" onClick={() => setActiveTab('settings')}>Ouvrir Paramètres</button>
              {!preflight?.ready && (
                // Un dimanche matin, rien ne doit bloquer : l'opérateur voit ce
                // qui manque, puis démarre en connaissance de cause.
                <button
                  className="vp-btn vp-btn--danger"
                  onClick={() => { setPreflightOpen(false); toggleListening() }}
                >
                  Démarrer quand même
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Messages et Alertes temporaires */}
      {(visibleRejection || micError) && (
        <div className="live-status-alerts flex gap-4 items-center px-4 py-2 bg-surface-1 border border-border-weak rounded-xl animate-fade-in">
          {visibleRejection && (
            <span className="live-ai-note">
              IA : « {visibleRejection.reference} » écartée ({visibleRejection.confidence}% &lt; {visibleRejection.threshold}%)
            </span>
          )}
          {micError && (
            <span className="live-ai-note is-error">
              {micError}
            </span>
          )}
        </div>
      )}
           <div className="live-main-grid">
        {/* ── COLONNE GAUCHE : CONSOLE AUDIO & RÉGLAGES ── */}
        <div className="live-col-left">
          {/* VU-Mètre Console */}
          <div className="vp-panel console-audio-panel flex-shrink-0">
            <span className="vp-label">Console Audio</span>
            
            {/* VU-mètre interactif en leds */}
            <div className="console-vumeter-wrap">
              <span className="vumeter-label text-[9px] font-mono tracking-widest text-[var(--text-faint)] uppercase">Input Level</span>
              <div className="vumeter-container">
                {Array.from({ length: 10 }).map((_, idx) => {
                  const activeLeds = isListening ? Math.round((volume / 100) * 10) : 0
                  const isOn = idx < activeLeds
                  let colorClass = 'green'
                  if (idx >= 8) colorClass = 'red'
                  else if (idx >= 6) colorClass = 'yellow'
                  
                  return (
                    <div 
                      key={idx} 
                      className={`vumeter-led ${isOn ? 'is-on' : ''} ${colorClass}`}
                    />
                  )
                })}
              </div>
              <span className="text-[10px] font-mono text-[var(--text-dim)]">
                {isListening ? `${volume}%` : 'SILENCE'}
              </span>
            </div>

            {/* Contrôle micro */}
            <div className="flex flex-col gap-2">
              <button 
                className={`vp-btn ${isListening ? 'vp-btn--ghost' : 'vp-btn--primary'} w-full py-1.5`} 
                onClick={handleToggleListening}
              >
                {isListening ? 'Arrêter Micro' : 'Démarrer Micro'}
              </button>
              
              <div className="text-[10px] text-[var(--text-dim)] truncate mt-1">
                {selectedAudioDevice?.label || 'Aucun micro actif'}
              </div>
            </div>
          </div>

          {/* Actions opérationnelles */}
          <div className="vp-panel flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <span className="vp-label">Sécurité</span>
              <span className={`vp-chip ${sundaySafeMode || shadowMode ? 'is-ok' : 'is-warn'}`}>
                {shadowMode ? 'Ombre' : sundaySafeMode ? 'Mode sûr' : 'Auto autorisé'}
              </span>
            </div>

            <button className="vp-btn vp-btn--sm w-full" onClick={() => { runPreflight(); setPreflightOpen(true) }}>
              Contrôle avant direct
            </button>
            <button className="vp-btn vp-btn--ghost vp-btn--sm w-full" onClick={() => setActiveTab('settings')}>
              Paramètres audio et moteurs
            </button>
            <button className="vp-btn vp-btn--danger vp-btn--sm w-full" onClick={activatePanicMode}>
              Arrêt d'urgence
            </button>

            <div className="flex flex-col gap-2 pt-2 border-t border-border-weak">
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full py-1.5" onClick={openProjectionWindow}>
                Écran Secours
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full py-1.5" onClick={openStageWindow}>
                Moniteur Scène
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full py-1.5" onClick={openObsWindow}>
                Source OBS/vMix
              </button>
            </div>
          </div>
        </div>

        {/* ── COLONNE CENTRALE : FILE DE VALIDATION LARGE ── */}
        <div className="live-col-center">
          <section className="vp-panel live-queue flex-1 flex flex-col min-height-0 overflow-hidden">
            <div className="live-queue-head flex-shrink-0">
              <h2>À valider <span className="count">{pendingItems.length}</span></h2>
              <div className="live-queue-tools">
                <span className="live-queue-hints">
                  <span className="vp-kbd">↑↓</span> naviguer
                  <span className="vp-kbd">Espace</span> projeter
                  <span className="vp-kbd">Échap</span> ignorer
                  <span className="vp-kbd">/</span> recherche
                </span>
                {projectionQueue.length > 0 && (
                  <button className="vp-btn vp-btn--ghost vp-btn--sm" onClick={clearProjectionQueue}>Vider</button>
                )}
              </div>
            </div>

            {/* Alerte ProPresenter */}
            {!propresenterConnected && !dismissedPpAlert && (
              <div className="live-alert animate-fade-in flex items-center justify-between p-3 mb-3 bg-warning-soft border border-warning rounded-xl text-xs gap-3">
                <div className="live-alert-body flex-1">
                  <strong className="text-[var(--warning)] font-bold block">Projection locale active</strong>
                  <span className="text-[var(--text-dim)] text-[11px]">ProPresenter déconnecté. L'écran de secours autonome sera utilisé.</span>
                  <button className="vp-btn vp-btn--ghost vp-btn--sm py-1 px-2 text-[var(--text-faint)]" onClick={() => {
                    setDismissedPpAlert(true)
                    try { localStorage.setItem('versepro_dismiss_pp_alert', 'true') } catch {}
                  }}>Masquer</button>
                </div>
              </div>
            )}

            <div className="live-queue-scroll flex-1 overflow-y-auto pr-1">
              {projectionQueue.length === 0 ? (
                <div className="live-empty">
                  <strong>Aucun verset en attente</strong>
                  <p>Démarrez le micro : les références citées pendant la prédication apparaîtront ici pour validation.</p>
                </div>
              ) : (
                <>
                  {pendingLocal.map((item) => renderCard(item, 'local'))}

                  {pendingLocal.length > 0 && pendingAi.length > 0 && (
                    <div className="live-queue-divider"><span className="vp-label">Suggestions IA</span></div>
                  )}

                  {pendingAi.map((item) => renderCard(item, 'ai'))}

                  {recentDone.length > 0 && (
                    <>
                      <div className="live-queue-divider"><span className="vp-label">Récents</span></div>
                      {recentDone.map((item) => (
                        <article 
                          key={item.queueId} 
                          className={`live-card is-done ${item.status === 'projected' ? 'is-projected' : ''}`}
                        >
                          <div className="live-card-head">
                            <span className="live-card-ref">{item.reference}</span>
                            <span className="live-card-badge is-muted">{item.status === 'projected' ? 'Projeté' : 'Ignoré'}</span>
                          </div>
                        </article>
                      ))}
                    </>
                  )}
                </>
              )}
            </div>
            
            {/* Barre de recherche manuelle intégrée au centre */}
            <div className="mt-3 pt-3 border-t border-border-weak flex-shrink-0 flex flex-col gap-2">
              <div className="flex gap-2">
                <input
                  ref={manualInputRef}
                  className="vp-input flex-1 py-1.5 text-sm"
                  type="text"
                  value={manualReference}
                  onChange={(e) => setManualReference(e.target.value)}
                  placeholder="Recherche ou référence directe (ex: Jn 3:16, Romains 8:28…)"
                  onKeyDown={(e) => e.key === 'Enter' && handleSendManual()}
                />
                <button className="vp-btn vp-btn--primary px-4 text-xs" onClick={handleSendManual} disabled={!manualReference.trim()}>Projeter</button>
              </div>
              <div className="live-quick-row flex gap-2 overflow-x-auto pb-1">
                {quickRefs.map((sug) => (
                  <button key={sug.ref} className="live-quick-chip text-[10px] px-2 py-0.5" onClick={() => sendReference(sug.ref)} title={`Projeter ${sug.ref} immédiatement`}>
                    {sug.label}
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* ── COLONNE DROITE : RETOUR ANTENNE (PROGRAM) & JOURNAL TRANSCRIPT ── */}
        <div className="live-col-right">
          {/* Section ON AIR */}
          <section className="vp-panel live-onair flex-shrink-0">
            <div className="live-onair-head">
              <span className={`live-onair-badge ${onAirDisplay ? 'is-live' : ''}`}>
                <span className="dot" />{onAirDisplay ? 'À l\'antenne' : 'Écran noir'}
              </span>
              <span className="live-onair-meta text-[10px]">
                {onAirDisplay?.at ? new Date(onAirDisplay.at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
            </div>
            <div className="live-onair-ref font-bold text-lg">{onAirDisplay?.reference || '—'}</div>
            <p
              className="live-onair-text"
              tabIndex={0}
              aria-label="Texte du verset projeté, zone défilable"
            >
              {onAirDisplay?.text || 'Aucun verset projeté.'}
            </p>
            
            {followMode && followProgress && (
              <div className="live-follow-bar mb-3" aria-label="Progression de la lecture">
                <div style={{ width: `${Math.round(followProgress.ratio * 100)}%` }} />
              </div>
            )}
            
            <div className="live-onair-controls grid grid-cols-2 gap-2">
              <button className="vp-btn vp-btn--sm py-1" onClick={() => handleShiftVerse(-1)} disabled={!canShift}>
                ← Préc.
              </button>
              <button className="vp-btn vp-btn--sm py-1" onClick={() => handleShiftVerse(1)} disabled={!canShift}>
                Suiv. →
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm py-1" onClick={clearProjectionScreen} disabled={!onAirDisplay}>
                Effacer
              </button>
              <button
                className={`vp-btn vp-btn--sm py-1 ${followMode ? 'vp-btn--primary' : 'vp-btn--ghost'}`}
                onClick={() => { lastAdvancedRef.current = null; setFollowMode((v) => !v) }}
                disabled={!canShift}
                aria-pressed={followMode}
                title={followMode
                  ? 'Désactiver l’avancement automatique à la fin du verset lu'
                  : 'Avancer automatiquement au verset suivant quand la lecture atteint la fin'}
              >
                Avance auto · {followMode ? 'ON' : 'OFF'}
              </button>
            </div>
          </section>

          {/* Section Journal de transcription */}
          <section className="vp-panel live-transcript-panel">
            <span className="vp-label px-3 pt-2">Transcript Direct</span>
            
            <div className="live-transcript-scroll" id="live-transcript-scroll">
              {currentTranscript ? (
                <p className="whitespace-pre-wrap">
                  {currentTranscript.split(' ').map((word, idx) => {
                    return <span key={idx}>{word} </span>
                  })}
                </p>
              ) : (
                <div className="text-[var(--text-faint)] italic text-center py-8">
                  En attente du signal micro...
                </div>
              )}
              <div ref={transcriptEndRef} />
            </div>
          </section>
        </div>
      </div>

      {/* ── RUBAN TEMPOREL DU CULTE (TIMELINE EN BAS) ── */}
      <div className="cult-timeline-panel">
        <span className="cult-timeline-title">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Ruban Temporel du Culte
        </span>
        <div className="cult-timeline-scroll">
          {projectionQueue.filter(item => item.status === 'projected').length === 0 ? (
            <span className="text-xs text-[var(--text-faint)] italic">Aucun jalon enregistré. Les versets projetés s'aligneront ici chronologiquement.</span>
          ) : (
            projectionQueue.filter(item => item.status === 'projected').map((item, idx) => {
              const isCurrent = onAirDisplay?.reference === item.reference
              const timeStr = item.detectedAt 
                ? new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) 
                : '10:00'
              
              return (
                <div 
                  key={idx}
                  className={`cult-timeline-item ${isCurrent ? 'is-current' : ''}`}
                  onClick={() => handleProjectFromQueue(item.queueId, item.reference, item.text)}
                  title="Cliquer pour reprojeter à l'antenne"
                >
                  <span className="cult-timeline-time">{timeStr}</span>
                  <span className="cult-timeline-ref">{item.reference}</span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ── BARRE D'ÉTAT INFÉRIEURE ── */}
      <footer className="live-statusbar">
        <div className="live-statusbar-left">
          <div className="live-statusbar-item">
            Moteur : <span className="text-[var(--vp-accent)] font-bold">{ASR_LABELS[asrMode] || 'Automatique'}</span>
          </div>
          <div className="live-statusbar-item">
            Flux : <span className="text-[var(--vp-ok)]">{isListening ? 'actif' : 'en veille'}</span>
          </div>
          <div className="live-statusbar-item">
            Session : <span className="text-[var(--text-dim)]">SQLite Active</span>
          </div>
        </div>
        
        <div className="live-statusbar-right">
          <span>VersePro v2.0 · Cockpit</span>
          {/* Chrono de session : durée du direct, pas l'heure (déjà en haut). */}
          <span className="global-clock" title="Durée de la session micro">
            {(() => {
              if (!listeningStartedAt) return '00:00:00'
              const end = isListening ? clock.getTime() : (listeningStoppedAt || clock.getTime())
              const total = Math.max(0, Math.floor((end - listeningStartedAt) / 1000))
              const h = String(Math.floor(total / 3600)).padStart(2, '0')
              const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
              const s = String(total % 60).padStart(2, '0')
              return `${h}:${m}:${s}`
            })()}
          </span>
        </div>
      </footer>
    </div>
  )
}
