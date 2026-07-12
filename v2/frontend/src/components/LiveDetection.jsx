import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useStore } from '../store.js'
import TranscriptTicker from './TranscriptTicker.jsx'

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
    isListening, setIsListening,
    currentTranscript,
    detectedReferences,
    propresenterConnected,
    sendReference, sendAudio,
    asrMode, selectedEngine, setSelectedEngine,
    activeBible, availableBibles, selectBible, fetchBibles,
    aiActive,
    translationLang, currentTranslation, setTranslationLang,
    autopilotMode, setAutopilotMode,
    projectionQueue, projectVerseFromQueue, rejectVerseFromQueue, clearProjectionQueue,
    connected,
    fetchSettings, updateSettings,
    voskStatus, fetchVoskStatus, downloadVoskModel,
    lastAiRejection,
    onAir, clearProjectionScreen,
    backendUnreachable,
    statistics,
    outputTheme, setOutputTheme,
    vmixEnabled, vmixHost, vmixPort, vmixInputId, updateVMixConfig
  } = useStore()

  const [manualReference, setManualReference] = useState('')
  const [selectedQueueIndex, setSelectedQueueIndex] = useState(0)
  const [volume, setVolume] = useState(0)
  const [audioDevices, setAudioDevices] = useState([])
  const [selectedAudioDeviceId, setSelectedAudioDeviceId] = useState(() => {
    try { return localStorage.getItem('versepro_audio_device_id') || '' } catch { return '' }
  })
  const [micPermissionState, setMicPermissionState] = useState('unknown')
  const [visibleRejection, setVisibleRejection] = useState(null)
  const [clock, setClock] = useState(() => new Date())
  const [micError, setMicError] = useState(null)
  const [followMode, setFollowMode] = useState(false)
  const lastAdvancedRef = useRef(null)

  const manualInputRef = useRef(null)
  const audioContextRef = useRef(null)
  const processorNodeRef = useRef(null)
  const streamRef = useRef(null)

  const refreshAudioDevices = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const inputs = devices.filter((device) => device.kind === 'audioinput')
      setAudioDevices(inputs)
      setSelectedAudioDeviceId((current) => {
        const saved = (() => {
          try { return localStorage.getItem('versepro_audio_device_id') || '' } catch { return '' }
        })()
        const next = current || saved || inputs[0]?.deviceId || ''
        if (next && inputs.some((device) => device.deviceId === next)) return next
        return inputs[0]?.deviceId || ''
      })
    } catch (error) {
      console.warn('Impossible de lire les entrées micro:', error)
    }
  }

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
    let animationId
    let phase = 0

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    const width = rect.width
    const height = rect.height

    const animate = () => {
      ctx.clearRect(0, 0, width, height)
      const amp = isListening ? Math.max(1.5, (volume / 100) * 12) : 0.6
      phase += isListening ? 0.06 + (volume / 100) * 0.08 : 0.015

      ctx.beginPath()
      ctx.strokeStyle = isListening ? 'rgba(123, 131, 235, 0.9)' : 'rgba(99, 102, 109, 0.4)'
      ctx.lineWidth = 1.4
      for (let x = 0; x < width; x++) {
        const envelope = Math.sin((x / width) * Math.PI)
        const y = height / 2 + Math.sin(x * 0.09 + phase) * amp * envelope
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      }
      ctx.stroke()
      animationId = requestAnimationFrame(animate)
    }
    animate()
    return () => cancelAnimationFrame(animationId)
  }, [isListening, volume])

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
        if (currentItem) projectVerseFromQueue(currentItem.queueId, currentItem.reference, currentItem.text)
      } else if (e.key === 'Escape' || e.key === 'Backspace') {
        e.preventDefault()
        if (currentItem) rejectVerseFromQueue(currentItem.queueId)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [pendingItems, selectedQueueIndex, projectVerseFromQueue, rejectVerseFromQueue])

  // Onboarding (première ouverture sans clé configurée)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardDeepgram, setOnboardDeepgram] = useState('')
  const [onboardAi, setOnboardAi] = useState('')
  const [submittingOnboard, setSubmittingOnboard] = useState(false)

  useEffect(() => {
    fetchBibles()
    fetchVoskStatus()
    refreshAudioDevices()

    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: 'microphone' })
        .then((permission) => {
          setMicPermissionState(permission.state)
          permission.onchange = () => setMicPermissionState(permission.state)
        })
        .catch(() => {})
    }

    const initSettings = async () => {
      const currentSettings = await fetchSettings()
      const ignored = localStorage.getItem('versepro_onboarding_ignored')
      if (currentSettings && !currentSettings.deepgram_api_key_configured && !ignored) {
        setShowOnboarding(true)
      }
    }
    initSettings()

    navigator.mediaDevices?.addEventListener?.('devicechange', refreshAudioDevices)
    const interval = setInterval(() => { fetchVoskStatus() }, 8000)
    return () => {
      stopRecording()
      clearInterval(interval)
      navigator.mediaDevices?.removeEventListener?.('devicechange', refreshAudioDevices)
    }
  }, [])

  // ── Capture micro ──────────────────────────────────────────────
  const downsampleBuffer = (buffer, inputSampleRate, outputSampleRate) => {
    if (inputSampleRate === outputSampleRate) return buffer
    const ratio = inputSampleRate / outputSampleRate
    const newLength = Math.round(buffer.length / ratio)
    const result = new Float32Array(newLength)
    let offsetResult = 0
    let offsetBuffer = 0
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
      let accum = 0, count = 0
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i]
        count++
      }
      result[offsetResult] = accum / count
      offsetResult++
      offsetBuffer = nextOffsetBuffer
    }
    return result
  }

  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Ce navigateur ne donne pas accès au micro.')
    }

    const audioConstraints = selectedAudioDeviceId
      ? {
          deviceId: { exact: selectedAudioDeviceId },
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        }
      : {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints })
    streamRef.current = stream
    setMicPermissionState('granted')
    refreshAudioDevices()

    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    const audioContext = new AudioContextClass()
    if (audioContext.state === 'suspended') await audioContext.resume()
    audioContextRef.current = audioContext

    const sourceNode = audioContext.createMediaStreamSource(stream)

    // Bande passante voix : coupe les basses (percussions) et les aigus (cymbales)
    const highpassNode = audioContext.createBiquadFilter()
    highpassNode.type = 'highpass'
    highpassNode.frequency.value = 250
    const lowpassNode = audioContext.createBiquadFilter()
    lowpassNode.type = 'lowpass'
    lowpassNode.frequency.value = 3000

    const inputSampleRate = audioContext.sampleRate

    // Traitement commun d'un bloc de samples (VU-mètre + rééchantillonnage + envoi)
    const handleAudioFrame = (inputData) => {
      if (!streamRef.current) return
      let sum = 0
      for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i]
      const rms = Math.sqrt(sum / inputData.length)
      setVolume(Math.min(100, Math.round(rms * 600)))

      const downsampled = downsampleBuffer(inputData, inputSampleRate, 16000)
      const pcmBuffer = new Int16Array(downsampled.length)
      for (let i = 0; i < downsampled.length; i++) {
        const s = Math.max(-1, Math.min(1, downsampled[i]))
        pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
      }
      sendAudio(pcmBuffer.buffer)
    }

    // Capture moderne : AudioWorklet (hors thread principal), repli ScriptProcessor
    let captureNode = null
    try {
      const workletCode = `
        class VpPcmForwarder extends AudioWorkletProcessor {
          constructor() { super(); this._chunks = []; this._length = 0 }
          process(inputs) {
            const channel = inputs[0] && inputs[0][0]
            if (channel) {
              this._chunks.push(new Float32Array(channel))
              this._length += channel.length
              if (this._length >= 4096) {
                const out = new Float32Array(this._length)
                let offset = 0
                for (const c of this._chunks) { out.set(c, offset); offset += c.length }
                this._chunks = []; this._length = 0
                this.port.postMessage(out, [out.buffer])
              }
            }
            return true
          }
        }
        registerProcessor('vp-pcm-forwarder', VpPcmForwarder)`
      const moduleUrl = URL.createObjectURL(new Blob([workletCode], { type: 'application/javascript' }))
      await audioContext.audioWorklet.addModule(moduleUrl)
      URL.revokeObjectURL(moduleUrl)
      captureNode = new AudioWorkletNode(audioContext, 'vp-pcm-forwarder')
      captureNode.port.onmessage = (event) => handleAudioFrame(event.data)
      console.info('Capture audio : AudioWorklet')
    } catch (workletErr) {
      console.warn('AudioWorklet indisponible, repli sur ScriptProcessor :', workletErr)
      captureNode = audioContext.createScriptProcessor(4096, 1, 1)
      captureNode.onaudioprocess = (event) => handleAudioFrame(event.inputBuffer.getChannelData(0))
    }
    processorNodeRef.current = captureNode

    sourceNode.connect(highpassNode)
    highpassNode.connect(lowpassNode)
    lowpassNode.connect(captureNode)
    captureNode.connect(audioContext.destination)
  }

  const stopRecording = () => {
    setVolume(0)
    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect()
      processorNodeRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }

  const toggleListening = async () => {
    if (isListening) {
      stopRecording()
      setIsListening(false)
    } else {
      try {
        setMicError(null)
        await startRecording()
        setIsListening(true)
      } catch (err) {
        console.error("Erreur d'accès micro:", err)
        setMicError(`Micro inaccessible : ${err.message}`)
      }
    }
  }

  // ── Actions ────────────────────────────────────────────────────
  const handleSendManual = async () => {
    const ref = manualReference.trim()
    if (!ref) return
    await sendReference(ref)
    setManualReference('')
  }

  const handleShiftVerse = async (delta) => {
    const next = shiftVerse(onAir?.reference, delta)
    if (next) await sendReference(next)
  }

  const handleOnboardSubmit = async (e) => {
    e.preventDefault()
    setSubmittingOnboard(true)
    try {
      const payload = {}
      if (onboardDeepgram.trim()) payload.deepgram_api_key = onboardDeepgram.trim()
      if (onboardAi.trim()) {
        if (onboardAi.trim().startsWith('AIza')) payload.gemini_api_key = onboardAi.trim()
        else payload.openrouter_api_key = onboardAi.trim()
      }
      if (Object.keys(payload).length > 0) await updateSettings(payload)
      setShowOnboarding(false)
    } finally {
      setSubmittingOnboard(false)
    }
  }

  const handleOnboardSkip = () => {
    localStorage.setItem('versepro_onboarding_ignored', 'true')
    setShowOnboarding(false)
  }

  const openProjectionWindow = () => {
    window.open('/output', 'VerseProProjection', 'width=1024,height=768,menubar=no,toolbar=no')
  }

  const openObsWindow = () => {
    window.open('/obs?theme=lower-third&bg=transparent', 'VerseProOBS', 'width=1280,height=720,menubar=no,toolbar=no')
  }

  const openStageWindow = () => {
    window.open('/stage', 'VerseProStage', 'width=1280,height=720,menubar=no,toolbar=no')
  }

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
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(`${proto}//${window.location.host}/ws/output`)
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

  const pendingLocal = pendingItems.filter((i) => i.source !== 'ai' && i.detectionMethod !== 'ai_semantic')
  const pendingAi = pendingItems.filter((i) => i.source === 'ai' || i.detectionMethod === 'ai_semantic')
  const recentDone = projectionQueue.filter((i) => i.status !== 'pending').slice(0, 3)
  const canShift = Boolean(shiftVerse(onAirDisplay?.reference, 1))
  const selectedAudioDevice = audioDevices.find((device) => device.deviceId === selectedAudioDeviceId)

  const renderCard = (item, accent) => {
    const pendingIdx = pendingItems.findIndex((p) => p.queueId === item.queueId)
    const isKeyboardActive = pendingIdx === selectedQueueIndex
    const confidencePct = item.confidence
      ? Math.round(item.confidence <= 1 ? item.confidence * 100 : item.confidence)
      : null

    return (
      <article
        key={item.queueId}
        className={`live-card ${accent === 'ai' ? 'is-ai' : ''} ${isKeyboardActive ? 'is-keyboard-active' : ''}`}
        onClick={() => setSelectedQueueIndex(pendingIdx)}
      >
        <div className="live-card-head">
          <span className="live-card-ref">{item.reference}</span>
          <span className={`live-card-badge ${accent === 'ai' ? 'is-ai' : 'is-local'}`}>
            {accent === 'ai' ? `Copilote ${confidencePct ?? 95}%` : 'Direct'}
          </span>
        </div>
        <p className="live-card-text">{item.text || 'Texte non chargé.'}</p>
        <div className="live-card-foot">
          <span className="live-card-time">
            {new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <div className="live-card-actions">
            <button
              className="vp-btn vp-btn--ghost vp-btn--sm"
              onClick={(e) => { e.stopPropagation(); rejectVerseFromQueue(item.queueId) }}
            >
              Ignorer
            </button>
            <button
              className={`vp-btn vp-btn--sm ${accent === 'ai' ? 'vp-btn--ai' : 'vp-btn--ok'}`}
              onClick={(e) => { e.stopPropagation(); projectVerseFromQueue(item.queueId, item.reference, item.text) }}
            >
              Projeter
            </button>
          </div>
        </div>
      </article>
    )
  }

  return (
    <div className="live-shell">
      {/* ═══════════ ONBOARDING ═══════════ */}
      {showOnboarding && (
        <div className="vp-modal-backdrop">
          <div className="vp-modal">
            <h2>Bienvenue sur VersePro</h2>
            <p style={{ marginTop: 8 }}>
              Ouvrez la régie maintenant en mode local. Vous pourrez ajouter Deepgram,
              OpenRouter ou Gemini plus tard depuis Paramètres.
            </p>

            <div className="vp-onboarding-value">
              <span className="vp-chip is-ok"><span className="dot" />Mode local prêt</span>
              <p>Le premier objectif est de voir la console fonctionner, sans mur de clés API.</p>
            </div>

            <button type="button" className="vp-btn vp-btn--primary vp-btn--wide" onClick={handleOnboardSkip}>
              Démarrer en mode local
            </button>

            <form onSubmit={handleOnboardSubmit} className="vp-onboarding-advanced">
              <details>
                <summary>Configurer les moteurs cloud maintenant</summary>

                <label>
                  <span className="vp-label" style={{ display: 'block', marginBottom: 6 }}>Clé API Deepgram — transcription cloud</span>
                  <input
                    className="vp-input"
                    type="password"
                    placeholder="dg_..."
                    value={onboardDeepgram}
                    onChange={(e) => setOnboardDeepgram(e.target.value)}
                  />
                </label>
                <label>
                  <span className="vp-label" style={{ display: 'block', marginBottom: 6 }}>Clé OpenRouter ou Gemini — détection IA</span>
                  <input
                    className="vp-input"
                    type="password"
                    placeholder="sk-or-... ou AIzaSy..."
                    value={onboardAi}
                    onChange={(e) => setOnboardAi(e.target.value)}
                  />
                </label>

                <button type="submit" className="vp-btn" disabled={submittingOnboard}>
                  {submittingOnboard ? 'Configuration…' : 'Enregistrer les clés'}
                </button>
              </details>

              <div className="vp-onboarding-vosk">
                <span className="vp-label" style={{ display: 'block', marginBottom: 8 }}>Moteur local Vosk (hors-ligne)</span>
                {voskStatus.installed ? (
                  <span className="vp-chip is-ok"><span className="dot" />Modèle {voskStatus.model_type} installé et prêt</span>
                ) : voskStatus.downloading ? (
                  <span className="vp-chip is-warn"><span className="dot" />Téléchargement du modèle en cours…</span>
                ) : (
                  <button type="button" className="vp-btn vp-btn--sm" onClick={downloadVoskModel}>
                    Télécharger le modèle français
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════ TOPBAR ═══════════ */}
      <header className="live-topbar">
        <div>
          <span className="vp-label">Projection</span>
          <h1>Live</h1>
          {visibleRejection && (
            <span className="live-ai-note animate-fade-in">
              IA : « {visibleRejection.reference} » écartée ({visibleRejection.confidence}% &lt; {visibleRejection.threshold}%)
            </span>
          )}
          {micError && (
            <span className="live-ai-note animate-fade-in" style={{ color: '#ffa39c', borderColor: 'rgba(255,69,58,0.3)', background: 'rgba(255,69,58,0.08)' }}>
              {micError}
            </span>
          )}
        </div>

        <div className="live-topbar-right">
          <span className={`vp-chip ${connected ? 'is-ok' : 'is-bad'}`}>
            <span className="dot" />{connected ? 'Serveur' : 'Hors ligne'}
          </span>
          <span className={`vp-chip ${asrMode === 'vosk' ? 'is-warn' : 'is-accent'}`}>
            <span className="dot" />{asrMode === 'vosk' ? 'Vosk local' : 'Deepgram'}
          </span>
          <span className={`vp-chip ${aiActive ? 'is-accent' : ''}`}>
            <span className="dot" />IA {aiActive ? 'active' : 'off'}
          </span>
          <span className={`vp-chip ${propresenterConnected ? 'is-ok' : 'is-warn'}`}>
            <span className="dot" />{propresenterConnected ? 'ProPresenter' : 'PP manuel'}
          </span>

          <span className="live-clock">
            {clock.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>

          <button className={`live-mic-main ${isListening ? 'is-live' : ''}`} onClick={toggleListening}>
            <span className="mic-dot" />
            {isListening ? 'LIVE' : 'Start'}
            <span className="mic-vu"><div style={{ width: `${isListening ? volume : 0}%` }} /></span>
          </button>
        </div>
      </header>

      {/* ═══════════ GRILLE PRINCIPALE ═══════════ */}
      {backendUnreachable && !connected && (
        <div className="vp-banner" role="alert">
          <strong>Serveur VersePro injoignable.</strong>
          <span>Vérifiez que le backend est démarré — reconnexion automatique en cours…</span>
        </div>
      )}
      <div className="live-main-grid">
        {/* ── Colonne principale : ON AIR + file ── */}
        <div className="live-col">
          <section className="vp-panel live-queue">
            <div className="live-queue-head">
              <h2>À valider <span className="count">{pendingItems.length}</span></h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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

            {!propresenterConnected && (
              <div className="live-alert animate-fade-in">
                <div style={{ flex: 1 }}>
                  <strong>ProPresenter non connecté</strong>
                  <span>La projection passe par l'écran de secours autonome — ouvrez-le sur le poste relié au vidéoprojecteur.</span>
                </div>
                <button className="vp-btn vp-btn--sm" onClick={openProjectionWindow}>Ouvrir l'écran</button>
              </div>
            )}

            <div className="live-queue-scroll">
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

                  {recentDone.length > 0 && pendingItems.length > 0 && (
                    <div className="live-queue-divider"><span className="vp-label">Traités</span></div>
                  )}
                  {recentDone.map((item) => (
                    <article key={item.queueId} className="live-card is-done">
                      <div className="live-card-head">
                        <span className="live-card-ref">{item.reference}</span>
                        <span className="live-card-badge is-muted">{item.status === 'projected' ? 'Projeté' : 'Ignoré'}</span>
                      </div>
                    </article>
                  ))}
                </>
              )}
            </div>
          </section>

          <section className="live-onair">
            <div className="live-onair-head">
              <span className={`live-onair-badge ${onAirDisplay ? 'is-live' : ''}`}>
                <span className="dot" />{onAirDisplay ? 'À l\'antenne' : 'Écran noir'}
              </span>
              <span className="live-onair-meta">
                {onAirDisplay?.at ? new Date(onAirDisplay.at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
            </div>
            <div className="live-onair-ref">{onAirDisplay?.reference || '—'}</div>
            <p className="live-onair-text">
              {onAirDisplay?.text || 'Aucun verset projeté. Validez une détection ou envoyez une référence manuelle.'}
            </p>
            {followMode && followProgress && (
              <div className="live-follow-bar" aria-label="Progression de la lecture">
                <div style={{ width: `${Math.round(followProgress.ratio * 100)}%` }} />
              </div>
            )}
            <div className="live-onair-actions">
              <button className="vp-btn vp-btn--sm" onClick={() => handleShiftVerse(-1)} disabled={!canShift} title="Verset précédent">
                ← Verset préc.
              </button>
              <button className="vp-btn vp-btn--sm" onClick={() => handleShiftVerse(1)} disabled={!canShift} title="Verset suivant — pour suivre une lecture de passage">
                Verset suiv. →
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm" onClick={clearProjectionScreen} disabled={!onAirDisplay}>
                Effacer l'écran
              </button>
              <button
                className={`vp-btn vp-btn--sm ${followMode ? 'vp-btn--primary' : 'vp-btn--ghost'}`}
                onClick={() => { lastAdvancedRef.current = null; setFollowMode((v) => !v) }}
                disabled={!canShift}
                title="Avance automatiquement au verset suivant quand la fin du verset affiché est lue au micro"
              >
                Suivi lecture {followMode ? 'ON' : 'OFF'}
              </button>
            </div>
          </section>
        </div>

        {/* ── Colonne secondaire : recherche manuelle + réglages ── */}
        <div className="live-col">
          <section className={`vp-panel live-audio-input ${isListening ? 'is-live' : ''}`}>
            <div className="live-audio-head">
              <div>
                <span className="vp-label">Entrée micro</span>
                <strong>{isListening ? 'Signal actif' : 'En attente'}</strong>
              </div>
              <span className={`live-audio-state ${isListening ? 'is-live' : ''}`}>
                <i />{isListening ? 'LIVE' : 'OFF'}
              </span>
            </div>

            <div className="live-audio-meter" aria-label="Niveau d'entrée micro">
              <div style={{ width: `${isListening ? volume : 0}%` }} />
            </div>

            <div className="live-audio-meta">
              <span>{selectedAudioDevice?.label || (micPermissionState === 'granted' ? 'Micro sélectionné' : 'Permission micro requise')}</span>
              <strong>{isListening ? `${volume}%` : micPermissionState === 'denied' ? 'Bloqué' : 'Prêt'}</strong>
            </div>

            <div className="live-audio-actions">
              <button className={`vp-btn ${isListening ? 'vp-btn--ghost' : 'vp-btn--primary'}`} onClick={toggleListening}>
                {isListening ? 'Arrêter' : 'Démarrer'}
              </button>
              <button className="vp-btn vp-btn--ghost" onClick={() => setActiveTab?.('settings')} disabled={isListening}>
                Choisir le micro
              </button>
            </div>
          </section>

          <section className={`vp-panel live-manual ${(!isListening || !connected) ? 'is-focus-mode' : ''}`}>
            <div className="live-manual-head">
              <span className="vp-label">Recherche manuelle</span>
              {(!isListening || !connected) ? (
                <span className="vp-label" style={{ color: 'var(--vp-accent)' }}>Mode principal</span>
              ) : (
                <span className="live-queue-hints"><span className="vp-kbd">⌘K</span> recherche avancée</span>
              )}
            </div>
            <div className="live-manual-row">
              <input
                ref={manualInputRef}
                className="vp-input"
                type="text"
                value={manualReference}
                onChange={(e) => setManualReference(e.target.value)}
                placeholder="Jn 3:16, Romains 8:28…"
                onKeyDown={(e) => e.key === 'Enter' && handleSendManual()}
              />
              <button className="vp-btn vp-btn--primary" onClick={handleSendManual} disabled={!manualReference.trim()}>Projeter</button>
            </div>
            <div className="live-quick-row">
              {quickRefs.map((sug) => (
                <button key={sug.ref} className="live-quick-chip" onClick={() => sendReference(sug.ref)} title={`Projeter ${sug.ref} immédiatement`}>
                  {sug.label}
                </button>
              ))}
            </div>
          </section>

          <section className="vp-panel live-plan">
            <div className="live-manual-head">
              <span className="vp-label">Plan de culte</span>
              {plan.length > 0 && (
                <button className="vp-btn vp-btn--ghost vp-btn--sm" onClick={() => savePlan([])}>Effacer</button>
              )}
            </div>
            <div className="live-manual-row" style={{ marginBottom: 0 }}>
              <input
                className="vp-input"
                type="text"
                value={planInput}
                onChange={(e) => setPlanInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addToPlan()}
                placeholder="Ajouter une lecture (Ps 23, Jn 14:1-6…)"
              />
              <button className="vp-btn" onClick={addToPlan} disabled={!planInput.trim()}>Ajouter</button>
            </div>
            {plan.length === 0 ? (
              <p className="live-plan-empty">Préparez ici les lectures du culte : elles se projettent ensuite dans l'ordre, d'un clic.</p>
            ) : (
              <div className="live-plan-list">
                {plan.map((item) => (
                  <div key={item.id} className={`live-plan-row ${item.done ? 'is-done' : ''}`}>
                    <strong>{item.ref}</strong>
                    <button className="vp-btn vp-btn--sm vp-btn--primary" onClick={() => projectPlanItem(item)}>
                      Projeter
                    </button>
                    <button
                      className="vp-btn vp-btn--ghost vp-btn--sm"
                      aria-label={`Retirer ${item.ref} du plan`}
                      onClick={() => savePlan(plan.filter((p) => p.id !== item.id))}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="vp-panel live-settings">
            <span className="vp-label">Réglages de session</span>

            <details className="live-settings-group" open>
              <summary>Audio</summary>
              <label>
                <span className="vp-label">Moteur vocal</span>
                <select className="vp-select" value={selectedEngine} onChange={(e) => setSelectedEngine(e.target.value)}>
                  <option value="auto">Auto (Deepgram + secours Vosk)</option>
                  <option value="deepgram">Deepgram cloud</option>
                  <option value="vosk">Vosk local (hors-ligne)</option>
                </select>
              </label>
            </details>

            <details className="live-settings-group">
              <summary>Bible & traduction</summary>
              <label>
                <span className="vp-label">Version biblique</span>
                <select className="vp-select" value={activeBible} onChange={(e) => selectBible(e.target.value)}>
                  {availableBibles.map((code) => (
                    <option key={code} value={code}>{code} — {BIBLE_NAMES[code] || code}</option>
                  ))}
                </select>
              </label>

              <label>
                <span className="vp-label">Traduction simultanée</span>
                <select className="vp-select" value={translationLang} onChange={(e) => setTranslationLang(e.target.value)} disabled={!aiActive}>
                  <option value="">Désactivée</option>
                  <option value="en">Anglais</option>
                  <option value="es">Espagnol</option>
                  <option value="de">Allemand</option>
                  <option value="pt">Portugais</option>
                </select>
              </label>
            </details>

            <details className="live-settings-group" open>
              <summary>Projection & Écrans</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <span className="vp-label" style={{ display: 'block', marginBottom: 6 }}>Mode de projection</span>
                  <div className="vp-segmented">
                    <button className={autopilotMode ? 'is-active' : ''} onClick={() => setAutopilotMode(true)}>
                      Autopilote
                    </button>
                    <button className={!autopilotMode ? 'is-active' : ''} onClick={() => setAutopilotMode(false)}>
                      Validation
                    </button>
                  </div>
                  <p style={{ fontSize: 11, color: 'var(--vp-text-faint)', marginTop: 7, lineHeight: 1.45 }}>
                    {autopilotMode
                      ? 'Les références explicites très fiables sont projetées directement. L\'IA reste en validation.'
                      : 'Toutes les détections passent par la file de validation.'}
                  </p>
                </div>

                <label>
                  <span className="vp-label">Thème d'affichage universel (Outputs)</span>
                  <select className="vp-select" value={outputTheme} onChange={(e) => setOutputTheme(e.target.value)}>
                    <option value="presentation">Presentation (Cinématique épuré)</option>
                    <option value="broadcast">Broadcast (Incrustations Lower Thirds)</option>
                    <option value="confidence">Stage/Confidence (Moniteur de scène)</option>
                    <option value="dual">Dual Language (Multi-traduction côte-à-côte)</option>
                    <option value="elegant">Élégant (Serif doré, cérémonie)</option>
                    <option value="minimal">Minimal (Typographie géante)</option>
                  </select>
                </label>
              </div>
            </details>

            <details className="live-settings-group">
              <summary>Pont vMix Title API</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={vmixEnabled} 
                    onChange={(e) => updateVMixConfig({ enabled: e.target.checked, host: vmixHost, port: vmixPort, input_id: vmixInputId })} 
                  />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>Activer le pont vMix</span>
                </label>
                <label>
                  <span className="vp-label">Adresse IP vMix</span>
                  <input 
                    type="text" 
                    className="vp-input" 
                    value={vmixHost} 
                    onChange={(e) => updateVMixConfig({ enabled: vmixEnabled, host: e.target.value, port: vmixPort, input_id: vmixInputId })} 
                    placeholder="127.0.0.1"
                  />
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
                  <label>
                    <span className="vp-label">Port API</span>
                    <input 
                      type="number" 
                      className="vp-input" 
                      value={vmixPort} 
                      onChange={(e) => updateVMixConfig({ enabled: vmixEnabled, host: vmixHost, port: Number(e.target.value), input_id: vmixInputId })} 
                      placeholder="8088"
                    />
                  </label>
                  <label>
                    <span className="vp-label">Entrée Titre vMix (Nom/ID)</span>
                    <input 
                      type="text" 
                      className="vp-input" 
                      value={vmixInputId} 
                      onChange={(e) => updateVMixConfig({ enabled: vmixEnabled, host: vmixHost, port: vmixPort, input_id: e.target.value })} 
                      placeholder="VerseProTitle"
                    />
                  </label>
                </div>
              </div>
            </details>

            <button className="vp-btn" onClick={openProjectionWindow}>
              Ouvrir l'écran de projection autonome
            </button>
            <button className="vp-btn vp-btn--ghost" onClick={openStageWindow}>
              Moniteur prédicateur (retour scène)
            </button>
            <button className="vp-btn vp-btn--ghost" onClick={openObsWindow}>
              Ouvrir la source OBS / vMix Web Browser
            </button>
          </section>
        </div>
      </div>

      {/* ═══════════ TICKER TRANSCRIPT ═══════════ */}
      <footer className={`vp-panel live-footer ${translationLang && currentTranslation ? 'has-translation' : ''}`}>
        {translationLang && currentTranslation && (
          <div className="live-translation">{currentTranslation}</div>
        )}
        <div className="live-ticker">
          <div className="live-ticker-label">
            <span className="vp-label">Transcript direct</span>
            <small>{asrMode === 'vosk' ? 'Vosk local' : 'Deepgram cloud'}</small>
          </div>
          <canvas id="vp-wave" className="live-ticker-wave" />
          <TranscriptTicker
            text={currentTranscript}
            placeholder="En attente du signal micro — la prédication s'affichera ici en direct."
          />
          <button
            type="button"
            className={`live-ticker-mic ${isListening ? 'is-active' : ''}`}
            onClick={toggleListening}
            aria-label={isListening ? 'Arrêter le micro' : 'Démarrer le micro'}
          >
            {isListening ? <StopIcon /> : <MicIcon />}
          </button>
        </div>
      </footer>
    </div>
  )
}
