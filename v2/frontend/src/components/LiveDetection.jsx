import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useStore } from '../store.js'
import liveStageImage from '../assets/versepro-live-stage.png'

const BIBLE_NAMES = {
  LSG: 'Louis Segond 1910',
  SEM: 'La Bible du Semeur',
  KJF: 'King James Française',
  NBS: 'Nouvelle Bible Segond',
  FC: 'Français Courant',
  TOB: 'Traduction Œcuménique (TOB)'
}

export default function LiveDetection() {
  const { 
    isListening, 
    setIsListening, 
    currentTranscript, 
    detectedReferences,
    propresenterConnected,
    autoSend,
    setAutoSend,
    sendReference,
    sendAudio,
    asrMode,
    selectedEngine,
    setSelectedEngine,
    activeBible,
    availableBibles,
    selectBible,
    fetchBibles,
    aiActive,
    translationLang,
    currentTranslation,
    setTranslationLang,
    autopilotMode,
    setAutopilotMode,
    projectionQueue,
    projectVerseFromQueue,
    rejectVerseFromQueue,
    clearProjectionQueue,
    connected,
    settings,
    fetchSettings,
    updateSettings,
    voskStatus,
    fetchVoskStatus,
    downloadVoskModel,
    lastAiRejection
  } = useStore()
  
  const [manualReference, setManualReference] = useState('')
  const [selectedRefIndex, setSelectedRefIndex] = useState(null)
  const [selectedQueueIndex, setSelectedQueueIndex] = useState(0)
  const [volume, setVolume] = useState(0)
  const [waveformBars, setWaveformBars] = useState(() => Array.from({ length: 28 }, () => 6))
  const [visibleRejection, setVisibleRejection] = useState(null)

  // Découper la transcription en mots récents pour l'effet de fading cognitif
  const displayTranscriptWords = useMemo(() => {
    if (!currentTranscript) return null
    const words = currentTranscript.trim().split(/\s+/).filter(Boolean)
    return words.slice(-30) // Ne garder que les 30 derniers mots
  }, [currentTranscript])

  // Dessin de l'onde Siri organique réactive (Bézier curves asservies au volume)
  useEffect(() => {
    const canvas = document.getElementById('siri-wave')
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    let animationId
    let phase = 0

    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      canvas.width = canvas.getBoundingClientRect().width * dpr
      canvas.height = canvas.getBoundingClientRect().height * dpr
      ctx.scale(dpr, dpr)
    }

    resize()
    window.addEventListener('resize', resize)

    const width = canvas.width / (window.devicePixelRatio || 1)
    const height = canvas.height / (window.devicePixelRatio || 1)

    const drawWave = (color, amplitude, frequency, offset) => {
      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.lineWidth = 1.0

      for (let x = 0; x < width; x++) {
        // Enveloppe gaussienne pour écraser les extrémités de l'onde à gauche/droite
        const envelope = Math.sin((x / width) * Math.PI)
        const y = (height / 2) + Math.sin(x * frequency + phase + offset) * amplitude * envelope

        if (x === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }
      ctx.stroke()
    }

    const animate = () => {
      ctx.clearRect(0, 0, width, height)

      // Asservir l'amplitude de l'onde au volume sonore dynamique du micro
      const baseAmp = isListening ? Math.max(1.5, (volume / 100) * 14) : 0.2
      const speed = isListening ? 0.05 + (volume / 100) * 0.08 : 0.015
      phase += speed

      if (isListening && baseAmp > 1.5) {
        // Tracé unique d'un pixel monochrome gris sombre (style Teenage Engineering / console audio pro)
        drawWave('rgba(29, 29, 31, 0.75)', baseAmp, 0.06, 0)
      } else {
        // Ligne plate d'attente neutre
        drawWave('rgba(142, 142, 147, 0.2)', 0.5, 0.02, 0)
      }

      animationId = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [isListening, volume])

  // Effacer la notification de rejet après 6 secondes
  useEffect(() => {
    if (lastAiRejection) {
      setVisibleRejection(lastAiRejection)
      const timer = setTimeout(() => {
        setVisibleRejection(null)
      }, 6000)
      return () => clearTimeout(timer)
    }
  }, [lastAiRejection])

  // Filtrage des éléments en attente (pending) pour la navigation par clavier
  const pendingItems = useMemo(() => {
    return projectionQueue.filter((item) => item.status === 'pending')
  }, [projectionQueue])

  // Ajustement de l'index sélectionné si le nombre d'éléments diminue
  useEffect(() => {
    if (selectedQueueIndex >= pendingItems.length) {
      setSelectedQueueIndex(Math.max(0, pendingItems.length - 1))
    }
  }, [pendingItems, selectedQueueIndex])

  // Écouteur pour les raccourcis claviers de la régie
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignorer si l'utilisateur saisit du texte dans un input
      if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') {
        return
      }

      if (pendingItems.length === 0) return

      const currentItem = pendingItems[selectedQueueIndex]

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedQueueIndex((prev) => Math.min(pendingItems.length - 1, prev + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedQueueIndex((prev) => Math.max(0, prev - 1))
      } else if (e.key === ' ' || e.key === 'Enter') {
        // Espace ou Entrée pour projeter
        e.preventDefault()
        if (currentItem) {
          projectVerseFromQueue(currentItem.queueId, currentItem.reference, currentItem.text)
        }
      } else if (e.key === 'Escape' || e.key === 'Backspace') {
        // Échap ou Retour arrière pour ignorer/rejeter
        e.preventDefault()
        if (currentItem) {
          rejectVerseFromQueue(currentItem.queueId)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [pendingItems, selectedQueueIndex, projectVerseFromQueue, rejectVerseFromQueue])
  
  // Onboarding local
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardDeepgram, setOnboardDeepgram] = useState('')
  const [onboardOpenRouter, setOnboardOpenRouter] = useState('')
  const [onboardGemini, setOnboardGemini] = useState('')
  const [submittingOnboard, setSubmittingOnboard] = useState(false)
  
  const audioContextRef = useRef(null)
  const processorNodeRef = useRef(null)
  const streamRef = useRef(null)

  useEffect(() => {
    fetchBibles()
    fetchVoskStatus()
    
    const initSettings = async () => {
      const currentSettings = await fetchSettings()
      const ignored = localStorage.getItem('versepro_onboarding_ignored')
      if (currentSettings && !currentSettings.deepgram_api_key_configured && !ignored) {
        setShowOnboarding(true)
      }
    }
    initSettings()
    
    // Intervalle pour vérifier le téléchargement de Vosk s'il tourne
    const interval = setInterval(async () => {
      const status = await fetchVoskStatus()
      if (status && !status.downloading) {
        // Optionnel : on peut arrêter l'intervalle si le téléchargement est fini
      }
    }, 8000)

    return () => {
      stopRecording()
      clearInterval(interval)
    }
  }, [])

  const downsampleBuffer = (buffer, inputSampleRate, outputSampleRate) => {
    if (inputSampleRate === outputSampleRate) {
      return buffer
    }
    const sampleRateRatio = inputSampleRate / outputSampleRate
    const newLength = Math.round(buffer.length / sampleRateRatio)
    const result = new Float32Array(newLength)
    let offsetResult = 0
    let offsetBuffer = 0
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio)
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

  const buildWaveformBars = (buffer, count = 28) => {
    const bucketSize = Math.max(1, Math.floor(buffer.length / count))
    return Array.from({ length: count }, (_, bucket) => {
      const start = bucket * bucketSize
      const end = Math.min(buffer.length, start + bucketSize)
      let sum = 0
      let peak = 0

      for (let i = start; i < end; i++) {
        const value = Math.abs(buffer[i])
        sum += value * value
        peak = Math.max(peak, value)
      }

      const rms = Math.sqrt(sum / Math.max(1, end - start))
      return Math.round(Math.min(96, Math.max(6, rms * 540 + peak * 100)))
    })
  }

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    const audioContext = new AudioContextClass()
    
    if (audioContext.state === 'suspended') {
      await audioContext.resume()
    }
    
    audioContextRef.current = audioContext
    
    const sourceNode = audioContext.createMediaStreamSource(stream)
    
    // Filtre passe-haut à 250Hz pour couper les basses, percussions et bruits de pas (rythme musical)
    const highpassNode = audioContext.createBiquadFilter()
    highpassNode.type = 'highpass'
    highpassNode.frequency.value = 250
    
    // Filtre passe-bas à 3000Hz pour couper les harmoniques aiguës, sifflements et cymbales
    const lowpassNode = audioContext.createBiquadFilter()
    lowpassNode.type = 'lowpass'
    lowpassNode.frequency.value = 3000
    
    const processorNode = audioContext.createScriptProcessor(4096, 1, 1)
    processorNodeRef.current = processorNode
    
    const inputSampleRate = audioContext.sampleRate
    const outputSampleRate = 16000
    
    processorNode.onaudioprocess = (event) => {
      if (!streamRef.current) return
      const inputData = event.inputBuffer.getChannelData(0)
      
      let sum = 0
      for (let i = 0; i < inputData.length; i++) {
        sum += inputData[i] * inputData[i]
      }
      const rms = Math.sqrt(sum / inputData.length)
      const volumeLevel = Math.min(100, Math.round(rms * 100 * 6))
      setVolume(volumeLevel)
      const nextWaveform = buildWaveformBars(inputData)
      setWaveformBars((previous) => nextWaveform.map((height, index) => {
        const prev = previous[index] || 6
        return Math.round(prev * 0.42 + height * 0.58)
      }))
      
      const downsampled = downsampleBuffer(inputData, inputSampleRate, outputSampleRate)
      
      const pcmBuffer = new Int16Array(downsampled.length)
      for (let i = 0; i < downsampled.length; i++) {
        const s = Math.max(-1, Math.min(1, downsampled[i]))
        pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
      }
      
      sendAudio(pcmBuffer.buffer)
    }
    
    // Connexion de la chaîne audio avec réduction de bruit vocal
    sourceNode.connect(highpassNode)
    highpassNode.connect(lowpassNode)
    lowpassNode.connect(processorNode)
    processorNode.connect(audioContext.destination)
  }

  const stopRecording = () => {
    setVolume(0)
    setWaveformBars(Array.from({ length: 28 }, () => 6))
    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect()
      processorNodeRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }
  
  const toggleListening = async () => {
    if (isListening) {
      stopRecording()
      setIsListening(false)
    } else {
      try {
        await startRecording()
        setIsListening(true)
      } catch (err) {
        console.error("Erreur d'accès micro:", err)
        alert("Impossible d'accéder au microphone : " + err.message)
      }
    }
  }
  
  const handleSendManual = async () => {
    if (manualReference) {
      await sendReference(manualReference)
      setManualReference('')
    }
  }
  
  const handleOnboardSubmit = async (e) => {
    e.preventDefault()
    setSubmittingOnboard(true)
    try {
      const payload = {}
      if (onboardDeepgram.trim()) payload.deepgram_api_key = onboardDeepgram.trim()
      if (onboardOpenRouter.trim()) payload.openrouter_api_key = onboardOpenRouter.trim()
      if (onboardGemini.trim()) payload.gemini_api_key = onboardGemini.trim()
      if (Object.keys(payload).length > 0) {
        await updateSettings(payload)
      }
      setShowOnboarding(false)
    } catch (err) {
      console.error("Erreur configuration onboarding:", err)
      alert("Impossible de sauvegarder la configuration : " + err.message)
    } finally {
      setSubmittingOnboard(false)
    }
  }

  const handleOnboardSkip = () => {
    localStorage.setItem('versepro_onboarding_ignored', 'true')
    setShowOnboarding(false)
  }
  
  const openProjectionWindow = () => {
    window.open('/projection', 'VerseProProjection', 'width=1024,height=768,menubar=no,toolbar=no')
  }

  const prompterLines = useMemo(() => {
    const source = currentTranscript || "En attente du signal micro. Les paroles reconnues defileront ici avec un fondu haut et bas pour garder le direct lisible."
    const words = source.trim().split(/\s+/).filter(Boolean)
    const lines = []
    for (let i = 0; i < words.length; i += 9) {
      lines.push(words.slice(i, i + 9).join(' '))
    }
    return lines.slice(-7)
  }, [currentTranscript])

  const latestReference = detectedReferences[0] || projectionQueue.find((item) => item.status === 'projected') || projectionQueue[0]
  const pendingCount = projectionQueue.filter((item) => item.status === 'pending').length
  const safetyMode = autopilotMode ? 'Autopilote local' : 'Validation manuelle'
  
  return (
    <div className="live-page-surface space-y-6">
      {showOnboarding && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(255, 255, 255, 0.75)', backdropFilter: 'blur(20px)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
          <div className="glass-copilot" style={{ maxWidth: '600px', width: '100%', padding: '40px', borderRadius: '16px', border: '1px solid #e3e3e3', boxShadow: '0 10px 30px rgba(0,0,0,0.08)', background: '#ffffff', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <span style={{ fontSize: '48px' }}>🚀</span>
              <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#1d1d1f', marginTop: '16px' }}>Bienvenue sur VersePro V2</h2>
              <p style={{ color: '#86868b', fontSize: '13px', marginTop: '8px' }}>
                Simplifiez la diffusion biblique de votre église. Découvrez l'interface régie instantanément grâce au mode local autonome, ou configurez vos clés cloud optionnelles.
              </p>
            </div>
            
            <form onSubmit={handleOnboardSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '6px' }}>
                  <small style={{ color: '#0071e3', fontWeight: 'bold', textTransform: 'uppercase', fontSize: '10px' }}>Clé API Deepgram (Optionnel)</small>
                  <input
                    type="password"
                    placeholder="dg_..."
                    value={onboardDeepgram}
                    onChange={(e) => setOnboardDeepgram(e.target.value)}
                    style={{ width: '100%', padding: '12px 16px', borderRadius: '12px', border: '1px solid #e3e3e3', background: '#f5f5f7', color: '#1d1d1f', marginTop: '4px' }}
                  />
                </label>
                <span style={{ fontSize: '11px', color: '#86868b' }}>Requis pour la transcription cloud. Si laissé vide, VersePro utilisera Vosk en local.</span>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '6px' }}>
                  <small style={{ color: '#b06000', fontWeight: 'bold', textTransform: 'uppercase', fontSize: '10px' }}>Clé API OpenRouter ou Gemini (IA Optionnelle)</small>
                  <input
                    type="password"
                    placeholder="sk-or-... ou AIzaSy..."
                    value={onboardOpenRouter}
                    onChange={(e) => setOnboardOpenRouter(e.target.value)}
                    style={{ width: '100%', padding: '12px 16px', borderRadius: '12px', border: '1px solid #e3e3e3', background: '#f5f5f7', color: '#1d1d1f', marginTop: '4px' }}
                  />
                </label>
                <span style={{ fontSize: '11px', color: '#86868b' }}>Active l'analyse des paraphrases par le moteur semantique (reglages modifiables plus tard).</span>
              </div>

              {/* MOTEUR VOSK LOCAL (ONBOARDING DÉPENDANCES) */}
              <div style={{ borderTop: '1px solid #e3e3e3', paddingTop: '16px', marginTop: '8px' }}>
                <span style={{ color: '#137333', fontWeight: 'bold', textTransform: 'uppercase', fontSize: '10px', display: 'block', marginBottom: '6px' }}>Reconnaissance vocale locale (Vosk)</span>
                
                {voskStatus.installed ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px', borderRadius: '12px', background: '#e6f4ea', border: '1px solid #ceead6', color: '#137333', fontSize: '12px' }}>
                    <span>✅</span>
                    <strong>Moteur local Vosk installé et prêt ({voskStatus.model_type})</strong>
                  </div>
                ) : voskStatus.downloading ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', borderRadius: '12px', background: '#fef7e0', border: '1px solid #feebc8', color: '#b06000', fontSize: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="animate-spin">📥</span>
                      <strong>Téléchargement et configuration du modèle Vosk...</strong>
                    </div>
                    <span style={{ fontSize: '11px', color: 'rgba(176,96,0,0.8)' }}>Le modèle est récupéré en tâche de fond. Le système s'initialisera automatiquement.</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <p style={{ color: '#86868b', fontSize: '12px' }}>
                      Pour faire fonctionner VersePro sans connexion Internet (mode local), vous devez installer le modèle linguistique français.
                    </p>
                    <button
                      type="button"
                      onClick={downloadVoskModel}
                      style={{ padding: '10px 14px', borderRadius: '10px', border: '1px solid #e3e3e3', background: '#ffffff', color: '#1d1d1f', cursor: 'pointer', fontWeight: 'bold', fontSize: '12px', width: 'fit-content', boxShadow: '0 1px 2px rgba(0,0,0,0.02)', transition: 'all 0.2s' }}
                    >
                      📥 Télécharger le modèle Vosk (Français)
                    </button>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '16px', borderTop: '1px solid #e3e3e3', paddingTop: '16px' }}>
                <button
                  type="submit"
                  disabled={submittingOnboard}
                  style={{ width: '100%', padding: '14px', borderRadius: '12px', border: 'none', background: '#0071e3', color: '#ffffff', cursor: 'pointer', fontWeight: 'bold', transition: 'all 0.2s', boxShadow: '0 4px 12px rgba(0, 113, 227, 0.2)' }}
                >
                  {submittingOnboard ? 'Configuration...' : 'Enregistrer et activer'}
                </button>
                
                <button
                  type="button"
                  onClick={handleOnboardSkip}
                  style={{ width: '100%', padding: '14px', borderRadius: '12px', border: '1px solid #e3e3e3', background: '#ffffff', color: '#1d1d1f', cursor: 'pointer', fontWeight: 'bold', transition: 'all 0.2s' }}
                >
                  Démarrer l'expérience en mode local (sans clés)
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <div className="live-unified-console">
        {/* En-tête de console unifiée */}
        <div className="live-stage-topbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <span className="live-eyebrow">Regie live</span>
            <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#1d1d1f' }}>Console de projection</h2>
            {visibleRejection && (
              <span className="live-ai-rejection-hint animate-fade-in" style={{ fontSize: '11px', color: '#b06000', fontStyle: 'italic', display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '6px', background: '#fff7e0', border: '1px solid #feebc8', padding: '4px 10px', borderRadius: '8px', userSelect: 'none' }}>
                🛡️ IA : suggestion "{visibleRejection.reference}" ignoree ({visibleRejection.confidence}% &lt; {visibleRejection.threshold}% requis)
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            {/* Indicateur micro miniaturisé */}
            <div className="live-mini-mic" onClick={toggleListening} style={{ cursor: 'pointer' }}>
              <span className={`live-mic-dot ${isListening ? 'is-active' : ''}`} />
              <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#1d1d1f' }}>
                {isListening ? 'Micro ouvert' : 'Micro en attente'}
              </span>
              <div className="live-mini-volume-bar">
                <div style={{ width: isListening ? `${volume}%` : '0%' }} />
              </div>
              <strong style={{ fontSize: '11px', color: '#1d1d1f', minWidth: '24px' }}>
                {isListening ? `${volume}%` : '0%'}
              </strong>
            </div>

            {/* Statuts simples */}
            <div className="live-status-row" style={{ display: 'flex', gap: '16px', alignItems: 'center', userSelect: 'none' }}>
              <span style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px', color: connected ? '#1e7e34' : '#d93025', fontWeight: '550' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: connected ? '#1e7e34' : '#d93025' }} />
                Serveur {connected ? 'connecte' : 'hors ligne'}
              </span>
              <span style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px', color: aiActive ? '#0071e3' : '#86868b', fontWeight: '550' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: aiActive ? '#0071e3' : '#86868b' }} />
                Detection IA {aiActive ? 'active' : 'inactive'}
              </span>
              <span style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px', color: propresenterConnected ? '#1e7e34' : '#86868b', fontWeight: '550' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: propresenterConnected ? '#1e7e34' : '#86868b' }} />
                ProPresenter {propresenterConnected ? 'pret' : 'manuel'}
              </span>
            </div>
          </div>
        </div>

        {/* Corps de la console unifiée */}
        <div className="live-console-body">
          {/* Colonne de gauche : Actions et Validation */}
          <div className="live-console-left">
            <div className="live-queue-modern" style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '24px', border: '1px solid #E5E7EB', borderRadius: '8px', background: '#ffffff' }}>
              <div className="live-queue-header" style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ color: '#1d1d1f', fontSize: '12px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>File de validation</span>
                    <span className="live-shortcut-hint" style={{ fontSize: '11px', color: '#86868b', background: '#f5f5f7', border: '1px solid #e3e3e3', padding: '2px 8px', borderRadius: '6px', fontWeight: 'normal' }}>
                      ⌨️ <code>↑/↓</code> naviguer • <code>Espace</code> projeter • <code>Échap</code> ignorer
                    </span>
                  </div>
                  <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#1d1d1f', marginTop: '4px' }}>{pendingCount} en attente</h3>
                </div>
                {projectionQueue.length > 0 && (
                  <button onClick={clearProjectionQueue} style={{ padding: '6px 12px', borderRadius: '8px', border: '1px solid #E5E7EB', background: '#ffffff', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer' }}>Vider la file</button>
                )}
              </div>

              {!propresenterConnected && (
                <div className="live-emergency-banner animate-fade-in" style={{ backgroundColor: '#fff3cd', border: '1px solid #ffeeba', color: '#856404', padding: '16px', borderRadius: '8px', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>⚠️</span>
                    <div>
                      <strong style={{ display: 'block', fontSize: '13px', color: '#856404' }}>Connexion ProPresenter inactive</strong>
                      <span style={{ fontSize: '11px', color: '#856404' }}>La liaison avec le logiciel de projection principal est perdue. activez la projection de secours locale.</span>
                    </div>
                  </div>
                  <button 
                    type="button"
                    onClick={openProjectionWindow}
                    style={{ width: '100%', padding: '10px 14px', border: 'none', background: '#d39e00', color: '#ffffff', fontWeight: 'bold', borderRadius: '8px', cursor: 'pointer', fontSize: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}
                  >
                    🖥️ Ouvrir l'Écran de Secours Local Autonome
                  </button>
                </div>
              )}

              {/* Conteneur de cartes avec hauteur fixe et défilement autonome */}
              <div className="live-queue-scroll-container" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '4px' }}>
                {projectionQueue.length === 0 ? (
                  <div className="live-empty-queue" style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#f5f5f7', border: '1px dashed #E5E7EB', borderRadius: '8px', padding: '24px' }}>
                    <span style={{ fontSize: '32px' }}>📡</span>
                    <strong style={{ display: 'block', marginTop: '12px', color: '#1d1d1f' }}>Aucun verset en attente</strong>
                    <p style={{ color: '#86868b', fontSize: '12px', textAlign: 'center', marginTop: '4px', maxWidth: '320px' }}>Les suggestions IA et les détections non déterministes s'afficheront ici en direct pour validation.</p>
                  </div>
                ) : (
                  <>
                    {/* 1. Les détections locales en attente */}
                    {pendingItems.filter(item => item.source !== 'ai' && item.detectionMethod !== 'ai_semantic').map((item) => {
                      const pendingIdx = pendingItems.findIndex((p) => p.queueId === item.queueId);
                      const isKeyboardActive = pendingIdx === selectedQueueIndex;
                      
                      return (
                        <article 
                          key={item.queueId} 
                          className={`live-queue-card is-${item.status} ${isKeyboardActive ? 'is-keyboard-active' : ''}`}
                          style={{ borderLeft: '4px solid #34c759', background: '#ffffff', padding: '16px', borderRadius: '8px', border: '1px solid #E5E7EB', borderLeftColor: '#34c759' }}
                          onClick={() => setSelectedQueueIndex(pendingIdx)}
                        >
                          <div className="live-queue-card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '15px', color: '#1d1d1f' }}>{item.reference}</strong>
                            <span className="live-local-badge" style={{ backgroundColor: 'rgba(52, 199, 89, 0.12)', color: '#137333', border: '1px solid rgba(52, 199, 89, 0.3)', padding: '2px 8px', borderRadius: '8px', fontSize: '10px', fontWeight: 'bold' }}>
                              ⚡ LOCAL
                            </span>
                          </div>
                          <p style={{ margin: '8px 0', fontSize: '13px', color: '#1d1d1f' }}>{item.text || 'Texte non chargé.'}</p>
                          <div className="live-queue-meta" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#86868b' }}>
                            <small>{new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small>
                            <small>{item.detectionMethod || 'local'}</small>
                          </div>

                          {item.status === 'pending' && (
                            <div className="live-queue-actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
                              <button 
                                onClick={(e) => { e.stopPropagation(); rejectVerseFromQueue(item.queueId); }}
                                style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #E5E7EB', background: '#ffffff', color: '#1d1d1f', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                              >
                                Ignorer
                              </button>
                              <button 
                                onClick={(e) => { e.stopPropagation(); projectVerseFromQueue(item.queueId, item.reference, item.text); }}
                                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', background: '#34c759', color: '#ffffff', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                              >
                                Projeter
                              </button>
                            </div>
                          )}
                        </article>
                      );
                    })}

                    {/* Séparateur s'il y a des détections locales ET des déductions IA */}
                    {pendingItems.filter(item => item.source !== 'ai' && item.detectionMethod !== 'ai_semantic').length > 0 && 
                     pendingItems.filter(item => item.source === 'ai' || item.detectionMethod === 'ai_semantic').length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '8px 0' }}>
                        <span style={{ fontSize: '9px', fontWeight: 'bold', color: '#86868b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Analyse contextuelle IA</span>
                        <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
                      </div>
                    )}

                    {/* 2. Les déductions IA en attente */}
                    {pendingItems.filter(item => item.source === 'ai' || item.detectionMethod === 'ai_semantic').map((item) => {
                      const confidencePercentage = item.confidence ? Math.round(item.confidence <= 1 ? item.confidence * 100 : item.confidence) : 95;
                      const pendingIdx = pendingItems.findIndex((p) => p.queueId === item.queueId);
                      const isKeyboardActive = pendingIdx === selectedQueueIndex;
                      
                      return (
                        <article 
                          key={item.queueId} 
                          className={`live-queue-card is-${item.status} ${isKeyboardActive ? 'is-keyboard-active' : ''}`}
                          style={{ borderLeft: '4px solid #af52de', background: '#ffffff', padding: '16px', borderRadius: '8px', border: '1px solid #E5E7EB', borderLeftColor: '#af52de' }}
                          onClick={() => setSelectedQueueIndex(pendingIdx)}
                        >
                          <div className="live-queue-card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '16px', color: '#1d1d1f' }}>{item.reference}</strong>
                            <span className="live-ai-badge" style={{ backgroundColor: 'rgba(175, 82, 222, 0.12)', color: '#8f39a7', border: '1px solid rgba(175, 82, 222, 0.3)', padding: '2px 8px', borderRadius: '8px', fontSize: '10px', fontWeight: 'bold' }}>
                              🤖 IA ({confidencePercentage}%)
                            </span>
                          </div>
                          <p style={{ margin: '8px 0', fontSize: '13px', color: '#1d1d1f' }}>{item.text || 'Texte non chargé.'}</p>
                          <div className="live-queue-meta" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#86868b' }}>
                            <small>{new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small>
                            <small>{item.requiresReview ? 'Validation requise' : 'IA'}</small>
                          </div>

                          {item.status === 'pending' && (
                            <div className="live-queue-actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
                              <button 
                                onClick={(e) => { e.stopPropagation(); rejectVerseFromQueue(item.queueId); }}
                                style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #E5E7EB', background: '#ffffff', color: '#1d1d1f', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                              >
                                Ignorer
                              </button>
                              <button 
                                onClick={(e) => { e.stopPropagation(); projectVerseFromQueue(item.queueId, item.reference, item.text); }}
                                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', background: '#af52de', color: '#ffffff', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' }}
                              >
                                Projeter
                              </button>
                            </div>
                          )}
                        </article>
                      );
                    })}
                    
                    {/* 3. Enfin les éléments projetés ou rejetés récents */}
                    {projectionQueue.filter(item => item.status !== 'pending').slice(0, 3).map((item) => {
                      return (
                        <article 
                          key={item.queueId} 
                          className={`live-queue-card is-${item.status}`}
                          style={{ borderLeft: item.status === 'projected' ? '4px solid #34c759' : '4px solid #8e8e93', opacity: 0.5, background: '#ffffff', padding: '16px', borderRadius: '8px', border: '1px solid #E5E7EB', borderLeftColor: item.status === 'projected' ? '#34c759' : '#8e8e93' }}
                        >
                          <div className="live-queue-card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '16px', color: '#1d1d1f' }}>{item.reference}</strong>
                            <span style={{ fontSize: '10px', fontWeight: 'bold', textTransform: 'uppercase', color: item.status === 'projected' ? '#34c759' : '#8e8e93' }}>
                              {item.status === 'projected' ? 'PROJETE' : 'IGNORE'}
                            </span>
                          </div>
                          <p style={{ margin: '8px 0', fontSize: '13px', color: '#1d1d1f' }}>{item.text || 'Texte non chargé.'}</p>
                        </article>
                      );
                    })}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Colonne de droite : Réglages & Retour Écran */}
          <div className="live-console-right">
            {/* Moniteur Écran de Retour live */}
            <div className="live-monitor-section" style={{ border: '1px solid #E5E7EB', borderRadius: '8px', overflow: 'hidden', background: '#000000', position: 'relative', height: '160px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div className="live-stage-backdrop" style={{ backgroundImage: `url(${liveStageImage})`, position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundSize: 'cover', backgroundPosition: 'center', opacity: 0.4 }} />
              <div className="live-stage-sheen" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'linear-gradient(to bottom, transparent, rgba(0,0,0,0.8))' }} />
              
              <div className="live-detection-console" style={{ position: 'relative', zIndex: 5, padding: '16px', width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', color: '#ffffff' }}>
                <div>
                  <span style={{ fontSize: '9px', fontWeight: 'bold', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Ecran de projection (Retour)</span>
                  <strong style={{ display: 'block', fontSize: '18px', color: '#ffffff', marginTop: '4px' }}>{latestReference?.reference || 'Noir'}</strong>
                </div>
                <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', margin: '4px 0 0' }}>
                  {latestReference?.text || 'Aucune référence projetée en direct.'}
                </p>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'rgba(255,255,255,0.4)' }}>
                  <span>{latestReference?.confidence ? `${Math.round(latestReference.confidence * 100)}% confiance` : ''}</span>
                  <span>{latestReference?.detection_method || 'pret'}</span>
                </div>
              </div>
            </div>

            {/* Panneau de contrôle et réglages */}
            <div className="live-control-section" style={{ border: '1px solid #E5E7EB', borderRadius: '8px', padding: '24px', background: '#ffffff', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <span style={{ color: '#86868b', fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Reglages de session</span>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
                <label className="live-control-card-compact" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '11px', color: '#86868b', fontWeight: 'bold' }}>Moteur vocal</span>
                  <select value={selectedEngine} onChange={(e) => setSelectedEngine(e.target.value)} style={{ padding: '8px', border: '1px solid #E5E7EB', borderRadius: '8px', background: '#f5f5f7', fontSize: '13px' }}>
                    <option value="auto">Auto (Vosk + Deepgram)</option>
                    <option value="deepgram">Deepgram cloud</option>
                    <option value="vosk">Vosk local</option>
                  </select>
                </label>

                <label className="live-control-card-compact" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '11px', color: '#86868b', fontWeight: 'bold' }}>Version biblique</span>
                  <select value={activeBible} onChange={(e) => selectBible(e.target.value)} style={{ padding: '8px', border: '1px solid #E5E7EB', borderRadius: '8px', background: '#f5f5f7', fontSize: '13px' }}>
                    {availableBibles.map((code) => (
                      <option key={code} value={code}>
                        {code} - {BIBLE_NAMES[code] || code}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="live-control-card-compact" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '11px', color: '#86868b', fontWeight: 'bold' }}>Traduction live</span>
                  <select value={translationLang} onChange={(e) => setTranslationLang(e.target.value)} disabled={!aiActive} style={{ padding: '8px', border: '1px solid #E5E7EB', borderRadius: '8px', background: '#f5f5f7', fontSize: '13px' }}>
                    <option value="">Desactivee</option>
                    <option value="en">Anglais</option>
                    <option value="es">Espagnol</option>
                    <option value="de">Allemand</option>
                    <option value="pt">Portugais</option>
                  </select>
                </label>
              </div>

              {/* Mode de projection segmented */}
              <div style={{ borderTop: '1px solid #E5E7EB', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: '#86868b', fontWeight: 'bold' }}>Mode de projection</span>
                <div className="live-segmented" style={{ width: '100%' }}>
                  <button onClick={() => setAutopilotMode(true)} className={autopilotMode ? 'is-active' : ''} style={{ flex: 1, padding: '8px', fontSize: '12px' }}>
                    Auto local
                  </button>
                  <button onClick={() => setAutopilotMode(false)} className={!autopilotMode ? 'is-active' : ''} style={{ flex: 1, padding: '8px', fontSize: '12px' }}>
                    Validation
                  </button>
                </div>
              </div>

              {/* Bouton de secours ProPresenter */}
              <button 
                onClick={openProjectionWindow} 
                className="live-ghost-button" 
                style={{ width: '100%', padding: '10px', fontSize: '12px', border: '1px solid #E5E7EB', background: '#ffffff', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}
              >
                🖥️ Ouvrir l'ecran de secours
              </button>
            </div>
          </div>
        </div>

        {/* Section de saisie et de transcription en bas (Flux et Recherche manuelle side-by-side) */}
        <div className="live-workbench-grid" style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px', margin: '20px 28px 0' }}>
          <section className="live-text-panel" style={{ height: '180px', display: 'flex', flexDirection: 'column', padding: '20px' }}>
            <span style={{ color: '#86868b', fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>Flux transcript écrit</span>
            <div style={{ flex: 1, overflowY: 'auto', fontSize: '13px', color: '#1d1d1f', lineHeight: '1.5' }} className={currentTranscript ? '' : 'is-empty'}>
              {currentTranscript || <span style={{ opacity: 0.4 }}>La transcription complete s'ecrit ici au fur et a mesure du culte...</span>}
            </div>
          </section>

          <section className={`live-text-panel is-manual ${(!isListening || !connected) ? 'is-emergency-highlight' : ''}`} style={{ height: '180px', display: 'flex', flexDirection: 'column', padding: '20px' }}>
            <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ color: '#86868b', fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Recherche manuelle</span>
              {(!isListening || !connected) && (
                <span style={{ color: '#0071e3', fontSize: '10px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ⚠️ Secours actif
                </span>
              )}
            </span>
            
            {(!isListening || !connected) && (
              <span style={{ color: '#0071e3', fontSize: '10px', display: 'block', marginBottom: '6px', lineHeight: '1.3', fontWeight: '500' }}>
                Micro inactif. Saisissez les references manuellement pour continuer.
              </span>
            )}
            
            <div className="live-manual-row" style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
              <input
                type="text"
                value={manualReference}
                onChange={(e) => setManualReference(e.target.value)}
                placeholder="Ex: Jn 3:16 ou Romains 8:28"
                onKeyPress={(e) => e.key === 'Enter' && handleSendManual()}
                style={{ flex: 1, padding: '8px 12px', border: '1px solid #E5E7EB', borderRadius: '8px', fontSize: '13px' }}
              />
              <button onClick={handleSendManual} style={{ padding: '8px 16px', background: '#1d1d1f', color: '#ffffff', border: 'none', borderRadius: '8px', fontSize: '13px', fontWeight: 'bold', cursor: 'pointer' }}>Envoyer</button>
            </div>
            
            <div className="live-quick-row" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {[
                { ref: "Jean 3:16", label: "Jn 3:16" },
                { ref: "Psaume 23:1", label: "Ps 23:1" },
                { ref: "Romains 8:28", label: "Rom 8:28" },
                { ref: "Éphésiens 2:8", label: "Eph 2:8" }
              ].map((sug) => (
                <button key={sug.ref} onClick={() => setManualReference(sug.ref)} style={{ padding: '6px 10px', background: '#f5f5f7', border: '1px solid #E5E7EB', borderRadius: '8px', fontSize: '11px', cursor: 'pointer', transition: 'all 0.1s' }}>
                  {sug.label}
                </button>
              ))}
            </div>
          </section>
        </div>

        {/* Ticker Prompteur Horizontal en bas */}
        <div className="live-prompter-ticker" style={{ margin: '20px 28px 28px' }}>
          <div className="live-ticker-label">
            <span>DIRECT TRANSCRIPT</span>
            <small>{asrMode === 'vosk' ? 'Vosk local' : 'Deepgram cloud'}</small>
          </div>
          
          <div style={{ width: '80px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', userSelect: 'none' }}>
            <canvas id="siri-wave" style={{ width: '100%', height: '100%', display: 'block' }} />
          </div>

          <div className="live-ticker-content">
            <div className="live-ticker-text">
              {displayTranscriptWords ? (
                displayTranscriptWords.map((word, idx) => {
                  const distance = displayTranscriptWords.length - 1 - idx
                  let opacity = 1.0
                  if (distance > 4) {
                    opacity = Math.max(0.22, 1.0 - (distance - 4) * 0.08)
                  }
                  const isRecent = distance <= 2
                  return (
                    <span 
                      key={`${word}-${idx}`} 
                      style={{ 
                        opacity, 
                        fontWeight: isRecent ? '750' : '550',
                        marginRight: '6px',
                        transition: 'all 0.3s ease',
                        display: 'inline-block',
                        color: isRecent ? '#1d1d1f' : '#86868b'
                      }}
                    >
                      {word}
                    </span>
                  )
                })
              ) : (
                <span style={{ opacity: 0.4 }}>En attente du signal micro. Le texte de la prédication s'affichera ici en direct.</span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={toggleListening}
            className={`live-ticker-mic-btn ${isListening ? 'is-active' : ''}`}
            aria-label={isListening ? 'Arreter le micro' : 'Demarrer le micro'}
            style={{ borderRadius: '8px', width: '38px', height: '38px', border: '1px solid #E5E7EB', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', transition: 'all 0.2s', flexShrink: 0, backgroundColor: isListening ? '#ff3b30' : '#ffffff', color: isListening ? '#ffffff' : '#1d1d1f' }}
          >
            {isListening ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
