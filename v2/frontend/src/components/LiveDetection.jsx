import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useStore } from '../store.js'
import { shallow } from 'zustand/shallow'
import TranscriptTicker from './TranscriptTicker.jsx'
import ChapterModal from './ChapterModal.jsx'
import BibleVersionsModal from './BibleVersionsModal.jsx'
import LiveHighlightIcon from './LiveHighlightIcons.jsx'
import FollowModal from './FollowModal.jsx'
import { BACKEND_BASE, BACKEND_WS_BASE, openExternal } from '../env.js'
import { versetsVoisins as calculerVoisins } from '../runtime/verse-window.js'

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
  nemotron: 'Nemotron local'
}

const METHOD_LABELS = {
  explicit: 'Référence',
  chapter_candidate: 'Chapitre',
  adjacent: 'Verset suivant',
  text_phrase: 'Citation connue',
  text_index: 'Texte exact',
  text_substring: 'Texte exact',
  text_fuzzy: 'Citation approchée',
  manual_exact: 'Fragment exact',
  manual_cross_verse: 'Passage exact',
  manual_approx: 'Fragment approché',
  manual_semantic: 'Paraphrase',
  ai_suggestion: 'Suggestion IA',
  ai_semantic: 'Suggestion IA',
}

/** Décale le numéro de verset d'une référence "Livre C:V" (navigation de lecture) */
function shiftVerse(reference, delta) {
  const match = /^(.+?)\s+(\d+):(\d+)/.exec(reference || '')
  if (!match) return null
  const verse = parseInt(match[3], 10) + delta
  if (verse < 1) return null
  return `${match[1]} ${match[2]}:${verse}`
}

/** Décale le numéro de chapitre d'une référence "Livre C:V" */
function shiftChapter(reference, delta) {
  const match = /^(.+?)\s+(\d+):(\d+)/.exec(reference || '')
  if (!match) return null
  const chap = parseInt(match[2], 10) + delta
  if (chap < 1) return null
  return `${match[1]} ${chap}:1`
}

/** Illumine les mots clés ou expressions prononcées dans le texte du verset (Paraphrase / Sémantique) */
function renderHighlightedVerseText(verseText, transcript, isParaphrase) {
  if (!verseText) return 'Texte non chargé.'
  if (!transcript || typeof transcript !== 'string' || !transcript.trim()) {
    return verseText
  }

  const STOP_WORDS = new Set(['dans', 'pour', 'avec', 'cette', 'celui', 'ceux', 'mais', 'donc', 'nous', 'vous', 'sont', 'sera', 'avez', 'était', 'alors', 'leurs'])
  const cleanTranscript = transcript.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w\s]/g, "")
  const transcriptWords = new Set(cleanTranscript.split(/\s+/).filter(w => w.length > 2 && !STOP_WORDS.has(w)))

  if (transcriptWords.size === 0) return verseText

  const tokens = verseText.split(/(\s+)/)

  return tokens.map((token, idx) => {
    const cleanToken = token.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w\s]/g, "")
    const isMatch = cleanToken.length > 2 && transcriptWords.has(cleanToken)

    if (isMatch) {
      return (
        <mark
          key={idx}
          className={`px-1 py-0.5 rounded font-semibold transition-all ${
            isParaphrase
              ? 'bg-amber-500/25 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/10'
              : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
          }`}
        >
          {token}
        </mark>
      )
    }
    return token
  })
}

/** Rend uniquement la portion sélectionnée en gras, le reste en graisse normale. */
function renderSelectedVerseText(verseText, selectedText) {
  const source = String(verseText || '')
  const selected = String(selectedText || '').trim().replace(/\s+/g, ' ')
  if (!source || !selected) return source || 'Texte non chargé.'

  // La sélection du navigateur peut contenir des espaces ou retours à la
  // ligne différents de ceux du texte biblique rendu dans la carte.
  const escapedWords = selected.split(/\s+/)
    .filter(Boolean)
    .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (!escapedWords.length) return source
  const match = new RegExp(escapedWords.join('\\s+'), 'i').exec(source)
  if (!match) return source

  const start = match.index
  const end = start + match[0].length
  return (
    <>
      {source.slice(0, start)}
      <strong className="live-selection-bold">{source.slice(start, end)}</strong>
      {source.slice(end)}
    </>
  )
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
    autoSend, setAutoSend,
    projectionQueue, projectVerseFromQueue, replaceQueuedVerse, rejectVerseFromQueue, clearDetectedVerses,
    previewSlide, previewBusy, previewReference, takePreview, clearPreview, fetchPreview,
    preparedVerses, planCount, prepareReference, projectPreparedVerse, removePreparedVerse, clearPreparedVerses,
    lastAiRejection,
    onAir, clearProjectionScreen,
    statistics,
    toggleListening, volume, waveform, audioDevices, selectedAudioDeviceId, micError, micSilent, refreshAudioDevices, setMicPermissionState,
    preflight, preflightLoading, runPreflight, activatePanicMode, sundaySafeMode, shadowMode,
    listeningStartedAt, listeningStoppedAt, addToast
  } = useStore(s => ({
    isListening: s.isListening,
    currentTranscript: s.currentTranscript,
    detectedReferences: s.detectedReferences,
    propresenterConnected: s.propresenterConnected,
    sendReference: s.sendReference, sendAudio: s.sendAudio,
    asrMode: s.asrMode, fetchBibles: s.fetchBibles,
    aiActive: s.aiActive,
    translationLang: s.translationLang, currentTranslation: s.currentTranslation, setTranslationLang: s.setTranslationLang,
    autoSend: s.autoSend, setAutoSend: s.setAutoSend,
    projectionQueue: s.projectionQueue, projectVerseFromQueue: s.projectVerseFromQueue, replaceQueuedVerse: s.replaceQueuedVerse, rejectVerseFromQueue: s.rejectVerseFromQueue, clearDetectedVerses: s.clearDetectedVerses,
    previewSlide: s.previewSlide, previewBusy: s.previewBusy, previewReference: s.previewReference, takePreview: s.takePreview, clearPreview: s.clearPreview, fetchPreview: s.fetchPreview,
    preparedVerses: s.preparedVerses, planCount: s.planCount, prepareReference: s.prepareReference, projectPreparedVerse: s.projectPreparedVerse, removePreparedVerse: s.removePreparedVerse, clearPreparedVerses: s.clearPreparedVerses,
    lastAiRejection: s.lastAiRejection,
    onAir: s.onAir, clearProjectionScreen: s.clearProjectionScreen,
    statistics: s.statistics,
    toggleListening: s.toggleListening, volume: s.volume, waveform: s.waveform, audioDevices: s.audioDevices, selectedAudioDeviceId: s.selectedAudioDeviceId, micError: s.micError, micSilent: s.micSilent, refreshAudioDevices: s.refreshAudioDevices, setMicPermissionState: s.setMicPermissionState,
    preflight: s.preflight, preflightLoading: s.preflightLoading, runPreflight: s.runPreflight, activatePanicMode: s.activatePanicMode, sundaySafeMode: s.sundaySafeMode, shadowMode: s.shadowMode,
    listeningStartedAt: s.listeningStartedAt, listeningStoppedAt: s.listeningStoppedAt,
    addToast: s.addToast
  }), shallow)

  const [manualReference, setManualReference] = useState('')
  // Longueur du chapitre à l'antenne : sans elle, impossible de savoir qu'on
  // est au DERNIER verset, donc impossible de décaler la bande de contexte.
  const [chapitreCourant, setChapitreCourant] = useState(null)
  // ENTRÉE PROJETTE-T-IL ? Le code la câblait sur la projection pendant que le
  // commentaire d'à côté affirmait le contraire (« Entrée = préparer sans
  // projection »). Deux intentions se sont succédé sans que l'une efface
  // l'autre, et plus personne ne savait ce que faisait la touche. On tranche
  // en le rendant EXPLICITE et réglable : par défaut Entrée projette, comme
  // le fait le code depuis toujours.
  // Densité de la file. Retenue d'un culte à l'autre : c'est une préférence
  // de régie, pas un état de session.
  const [fileCompacte, setFileCompacte] = useState(() => {
    try { return localStorage.getItem('versepro_file_compacte') === 'oui' } catch { return false }
  })
  const basculerDensite = () => {
    setFileCompacte((actuel) => {
      const suivant = !actuel
      try { localStorage.setItem('versepro_file_compacte', suivant ? 'oui' : 'non') } catch {}
      return suivant
    })
  }

  const [entreeProjette, setEntreeProjette] = useState(() => {
    try { return localStorage.getItem('versepro_entree_projette') !== 'non' } catch { return true }
  })
  const basculerEntree = () => {
    setEntreeProjette((actuel) => {
      const suivant = !actuel
      try { localStorage.setItem('versepro_entree_projette', suivant ? 'oui' : 'non') } catch {}
      return suivant
    })
  }
  const [selectedQueueIndex, setSelectedQueueIndex] = useState(0)
  const [visibleRejection, setVisibleRejection] = useState(null)
  const [clock, setClock] = useState(() => new Date())
  const [followMode, setFollowMode] = useState(false)
  const [preflightOpen, setPreflightOpen] = useState(false)
  const [followModalOpen, setFollowModalOpen] = useState(false)
  const [projectingIds, setProjectingIds] = useState(new Set())
  const [flippingIds, setFlippingIds] = useState(new Set())
  const [annotationSelections, setAnnotationSelections] = useState({})
  const [annotationBusy, setAnnotationBusy] = useState(false)
  const [failedIds, setFailedIds] = useState(new Set())
  const [preparingReference, setPreparingReference] = useState(false)
  const [activeHighlightColor, setActiveHighlightColor] = useState(null)
  const [previewDeplie, setPreviewDeplie] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [chapterModalRef, setChapterModalRef] = useState(null)
  const [versionsModalOpen, setVersionsModalOpen] = useState(false)
  const queueScrollRef = useRef(null)

  // Suggestions d'autocomplétion pour la barre de recherche manuelle
  const [manualSuggestions, setManualSuggestions] = useState([])
  const [manualSearching, setManualSearching] = useState(false)
  const [manualActiveIndex, setManualActiveIndex] = useState(0)
  const [showManualSuggestions, setShowManualSuggestions] = useState(false)
  const manualDebounceRef = useRef(null)
  const manualSeqRef = useRef(0)
  const manualBarRef = useRef(null)

  const [dismissedPpAlert, setDismissedPpAlert] = useState(() => {
    try { return localStorage.getItem('versepro_dismiss_pp_alert') === 'true' } catch { return false }
  })
  const lastAdvancedRef = useRef(null)
  const advanceTimerRef = useRef(null)

  const { activeBible, availableBibles, undoLastProjection, selectedEngine, setSelectedEngine } = useStore(s => ({
    activeBible: s.activeBible, availableBibles: s.availableBibles, undoLastProjection: s.undoLastProjection, selectedEngine: s.selectedEngine, setSelectedEngine: s.setSelectedEngine
  }), shallow)
  const [compareOpen, setCompareOpen] = useState(false)
  const [comparePreviews, setComparePreviews] = useState(null)

  // Effet d'auto-scroll automatique vers le dernier verset (en bas de liste)
  useEffect(() => {
    if (autoScroll && queueScrollRef.current) {
      queueScrollRef.current.scrollTo({ top: queueScrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [projectionQueue, currentTranscript, autoScroll])

  // Raccourci global Cmd+Z / Ctrl+Z (Annulation immédiate de projection / version)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        // Empêche le comportement d'annulation natif du champ texte si on n'est pas dans un input
        if (!['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
          e.preventDefault()
          undoLastProjection()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [undoLastProjection])

  // Détection vocale ASR non-automatique des demandes de version
  const voiceSuggestedVersion = useMemo(() => {
    if (!currentTranscript) return null
    const lower = currentTranscript.toLowerCase()
    let detected = null
    if (lower.includes('semeur') || lower.includes('bible du semeur')) detected = 'SEM'
    else if (lower.includes('tob') || lower.includes('œcuménique')) detected = 'TOB'
    else if (lower.includes('king james') || lower.includes('kjf')) detected = 'KJF'
    else if (lower.includes('français courant') || lower.includes('bfc')) detected = 'FC'
    else if (lower.includes('nouvelle bible segond') || lower.includes('nbs')) detected = 'NBS'
    else if (lower.includes('louis segond') || lower.includes('segond 1910')) detected = 'LSG'

    const currentOnAirVersion = onAir?.version || activeBible || 'LSG'
    if (detected === currentOnAirVersion) return null // No-Op si déjà actif !
    return detected
  }, [currentTranscript, onAir, activeBible])

  const handleSwitchVersion = async (targetVersion) => {
    if (!onAirDisplay?.reference) return
    const currentOnAirVersion = onAirDisplay?.version || activeBible || 'LSG'
    if (targetVersion === currentOnAirVersion) return // Smart No-Op !

    await sendReference(onAirDisplay.reference, targetVersion)
  }

  const toggleCompareMode = async (ref) => {
    if (compareOpen) {
      setCompareOpen(false)
      return
    }
    setCompareOpen(true)
    try {
      const resp = await fetch(`${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(ref)}&limit=1`)
      const data = await resp.json()
      if (data?.results?.[0]?.translations) {
        setComparePreviews(data.results[0].translations)
      }
    } catch {
      setComparePreviews(null)
    }
  }

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
    const liveWave = styles.getPropertyValue('--color-wave-live').trim() || '#3b82f6'
    const idleWave = styles.getPropertyValue('--color-wave-idle').trim() || '#64748b'

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

  // Fait défiler uniquement le journal, jamais la page entière.
  //
  // Défilement INSTANTANÉ, et c'est délibéré. En « smooth », chaque partiel
  // — Deepgram en envoie plusieurs par seconde — interrompait l'animation
  // précédente en plein vol pour en relancer une depuis sa position courante.
  // Le défilement n'aboutissait jamais : c'est ce qui donnait l'impression
  // d'une transcription saccadée. En instantané, le texte grandit de façon
  // continue et le bas reste collé, ce qui se lit comme un flux régulier.
  useEffect(() => {
    const scroll = document.getElementById('live-transcript-scroll')
    if (scroll) scroll.scrollTop = scroll.scrollHeight
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
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)

      if (e.key === '/' && !typing) {
        e.preventDefault()
        manualInputRef.current?.focus()
        return
      }
      if (typing) return

      // « T » comme take : envoyer la préparation, même file vide — c'est
      // justement quand rien n'est détecté que l'opérateur monte à la main.
      if (e.key.toLowerCase() === 't' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        takePreview()
        return
      }
      if (pendingItems.length === 0) return

      const currentItem = pendingItems[selectedQueueIndex]
      if (e.key.toLowerCase() === 'p') {
        e.preventDefault()
        if (currentItem) previewReference(currentItem.reference)
        return
      }
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
  }, [pendingItems, selectedQueueIndex, projectVerseFromQueue, rejectVerseFromQueue, takePreview, previewReference])

  useEffect(() => {
    fetchBibles()
    refreshAudioDevices()
    runPreflight()
    fetchPreview()

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

  // Fermeture des suggestions manuelles lors d'un clic extérieur
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (manualBarRef.current && !manualBarRef.current.contains(e.target)) {
        setShowManualSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // ── Actions ────────────────────────────────────────────────────
  const handleManualInputChange = (val) => {
    setManualReference(val)
    clearTimeout(manualDebounceRef.current)
    const trimmed = val.trim()
    if (trimmed.length < 2) {
      setManualSuggestions([])
      setShowManualSuggestions(false)
      return
    }

    manualDebounceRef.current = setTimeout(async () => {
      const seq = ++manualSeqRef.current
      setManualSearching(true)
      try {
        const response = await fetch(`${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(trimmed)}&limit=6`)
        const data = await response.json()
        if (seq === manualSeqRef.current) {
          const res = data.results || []
          setManualSuggestions(res)
          setManualActiveIndex(0)
          setShowManualSuggestions(res.length > 0)
        }
      } catch {
        if (seq === manualSeqRef.current) setManualSuggestions([])
      } finally {
        if (seq === manualSeqRef.current) setManualSearching(false)
      }
    }, 150)
  }

  const handleSendManual = async () => {
    const ref = manualReference.trim()
    if (!ref) return
    setShowManualSuggestions(false)
    await sendReference(ref)
    setManualReference('')
  }

  const handlePrepareManual = async () => {
    const ref = manualReference.trim()
    if (!ref || preparingReference) return
    setShowManualSuggestions(false)
    setPreparingReference(true)
    try {
      const prepared = await prepareReference(ref)
      if (prepared) setManualReference('')
    } finally {
      setPreparingReference(false)
    }
  }

  const handleToggleListening = async () => {
    if (isListening) {
      await toggleListening()
      return
    }
    const result = await runPreflight({ probeCloud: true, requireMicro: true })
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

  const handleProjectPrepared = async (item) => {
    setProjectingIds((prev) => new Set(prev).add(item.id))
    try {
      await projectPreparedVerse(item.id)
    } finally {
      setProjectingIds((prev) => {
        const next = new Set(prev)
        next.delete(item.id)
        return next
      })
    }
  }

  const handleAdjacentVerse = async (item, reference) => {
    if (!reference || item.status !== 'pending' || flippingIds.has(item.queueId)) return
    setFlippingIds((prev) => new Set(prev).add(item.queueId))
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(reference)}&limit=1`)
      const data = await response.json().catch(() => ({}))
      const match = data.results?.[0]
      if (!response.ok || !match?.reference || !match?.text) {
        throw new Error(data?.detail || `Verset introuvable : ${reference}`)
      }
      // Attend le milieu de la rotation : la carte disparaît brièvement,
      // puis réapparaît avec le nouveau contenu au même emplacement.
      await new Promise((resolve) => setTimeout(resolve, 210))
      replaceQueuedVerse(item.queueId, match)
      await new Promise((resolve) => setTimeout(resolve, 210))
    } catch (error) {
      addToast?.({ message: error.message || 'Impossible de charger le verset suivant', kind: 'error' })
    } finally {
      setFlippingIds((prev) => {
        const next = new Set(prev)
        next.delete(item.queueId)
        return next
      })
    }
  }

  const handleTextSelection = (event, selectionKey) => {
    const selection = window.getSelection?.()
    if (!selection || selection.isCollapsed) return
    const container = event.currentTarget
    if (!container.contains(selection.anchorNode) || !container.contains(selection.focusNode)) return
    const selected = selection.toString().replace(/\s+/g, ' ').trim()
    if (!selected) return
    setAnnotationSelections((previous) => ({ ...previous, [selectionKey]: selected }))
  }

  const clearTextSelection = (queueId) => {
    setAnnotationSelections((previous) => {
      const next = { ...previous }
      delete next[queueId]
      return next
    })
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

  const onAirDisplay = (onAir && onAir.reference) ? onAir : (() => {
    const projected = projectionQueue.find((item) => item.status === 'projected')
    return projected ? { reference: projected.reference, text: projected.text, version: projected.version || activeBible } : null
  })()
  const onAirSelectionKey = onAirDisplay?.reference
    ? `onair:${onAirDisplay.reference}:${onAirDisplay.version || activeBible || 'LSG'}`
    : 'onair:none'
  const onAirSelectedText = annotationSelections[onAirSelectionKey] || ''

  const sendLiveAnnotation = async (type = 'clear') => {
    if (annotationBusy || (!onAirSelectedText && type !== 'clear')) return
    const annotationConfig = {
      highlight: { color: 'yellow', success: 'Surlignage appliqué à la projection' },
      underline: { color: 'red', success: 'Soulignage appliqué à la projection' },
      circle: { color: '#38bdf8', success: 'Cercle appliqué à la projection' },
    }
    const config = annotationConfig[type]
    const annotations = config
      ? [{ type, color: config.color, text: onAirSelectedText, bold: true }]
      : []

    setAnnotationBusy(true)
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/annotation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'La sortie de projection ne répond pas')
      if (!config) clearTextSelection(onAirSelectionKey)
      window.getSelection?.()?.removeAllRanges?.()
      addToast?.({ message: config?.success || 'Annotations effacées', kind: config ? 'success' : 'info' })
    } catch (error) {
      addToast?.({ message: error.message || 'Impossible d’annoter la projection', kind: 'error' })
    } finally {
      setAnnotationBusy(false)
    }
  }

  // Navigation dynamique autour du verset actuellement projeté à l'antenne
  const onAirNavChips = useMemo(() => {
    if (!onAirDisplay?.reference) return null
    const ref = onAirDisplay.reference
    const prevV = shiftVerse(ref, -1)
    const nextV = shiftVerse(ref, 1)
    const prevC = shiftChapter(ref, -1)
    const nextC = shiftChapter(ref, 1)
    const match = /^(.+?)\s+(\d+):(\d+)/.exec(ref || '')
    const bookName = match ? match[1] : ''
    const chapNum = match ? parseInt(match[2], 10) : 1
    const verseNum = match ? parseInt(match[3], 10) : 1

    return {
      ref,
      bookName,
      chapNum,
      verseNum,
      prevV: prevV ? { ref: prevV, label: `◄ Verset ${verseNum - 1}` } : null,
      nextV: nextV ? { ref: nextV, label: `Verset ${verseNum + 1} ►` } : null,
      prevC: prevC ? { ref: prevC, label: `◄ Chap. ${chapNum - 1}` } : null,
      nextC: nextC ? { ref: nextC, label: `Chap. ${chapNum + 1} ►` } : null,
    }
  }, [onAirDisplay])

  // Longueur du chapitre à l'antenne. /api/v1/bible/chapter existait dans les
  // appels de ChapterModal mais pas dans le backend : la route vient d'être
  // créée, et c'est elle qui donne le nombre de versets.
  useEffect(() => {
    const ref = onAirDisplay?.reference
    if (!ref) { setChapitreCourant(null); return }
    let annule = false
    const version = onAirDisplay?.version || activeBible || ''
    fetch(`${BACKEND_BASE}/api/v1/bible/chapter?q=${encodeURIComponent(ref)}&version=${version}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!annule && d?.count) setChapitreCourant(d) })
      .catch(() => {})
    return () => { annule = true }
  }, [onAirDisplay?.reference, onAirDisplay?.version, activeBible])

  // LA BANDE DE CONTEXTE — dix versets autour de celui qui est à l'antenne :
  // 5 versets avant et 5 versets après.
  // Si v=1 (premier verset) : 10 versets suivants.
  // Si v=dernier : 10 versets précédents.
  const versetsVoisins = useMemo(() => {
    const courant = onAirNavChips?.verseNum
    if (!courant || !onAirNavChips?.bookName) return null
    const total = chapitreCourant?.count || Math.max(courant + 10, 50)
    const numeros = calculerVoisins(courant, total)
    return numeros.length ? { numeros, courant, total: chapitreCourant?.count || total } : null
  }, [chapitreCourant, onAirNavChips])

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

  useEffect(() => {
    if (sundaySafeMode && followMode) {
      clearTimeout(advanceTimerRef.current)
      advanceTimerRef.current = null
      setFollowMode(false)
      lastAdvancedRef.current = null
    }
  }, [sundaySafeMode, followMode])

  // Auto-avance : quand la fin du verset est lue, projette le suivant (une seule fois par verset)
  useEffect(() => {
    if (sundaySafeMode || !followMode || !followProgress?.tailReached || !onAirDisplay?.reference) return
    if (lastAdvancedRef.current === onAirDisplay.reference) return
    lastAdvancedRef.current = onAirDisplay.reference
    advanceTimerRef.current = setTimeout(() => {
      advanceTimerRef.current = null
      handleShiftVerse(1)
    }, 700)
    return () => {
      clearTimeout(advanceTimerRef.current)
      advanceTimerRef.current = null
    }
  }, [sundaySafeMode, followMode, followProgress, onAirDisplay])

  const handlePanic = async () => {
    clearTimeout(advanceTimerRef.current)
    advanceTimerRef.current = null
    setFollowMode(false)
    lastAdvancedRef.current = null
    await activatePanicMode()
  }

  const isSemanticSuggestion = (item) => (
    ['ai', 'semantic'].includes(item.source)
    || ['ai_semantic', 'semantic_local'].includes(item.detectionMethod)
  )
  const displayQueue = useMemo(() => {
    const pending = projectionQueue.filter((item) => item.status === 'pending')
    // Les éléments projetés étaient auparavant filtrés entièrement : la carte
    // « À l'antenne » n'était donc jamais rendue et ses commandes
    // d'annotation restaient invisibles. On conserve le dernier élément
    // projeté, ou crée une carte légère quand l'envoi a été fait manuellement.
    const projected = [...projectionQueue].reverse().find((item) => (
      item.status === 'projected' && (!onAir?.reference || item.reference === onAir.reference)
    ))
    const active = projected || (onAir?.reference ? {
      queueId: `onair_${onAir.reference}`,
      reference: onAir.reference,
      text: onAir.text || '',
      version: onAir.version || activeBible,
      detectedAt: onAir.at || new Date().toISOString(),
      source: 'local',
      detectionMethod: 'manual',
      status: 'projected'
    } : null)
    const pendingWithoutActive = active
      ? pending.filter((item) => item.reference !== active.reference)
      : pending
    return active ? [...pendingWithoutActive, active] : pending
  }, [projectionQueue, onAir, activeBible])
  
  const projectedHistory = projectionQueue.filter((item) => item.status === 'projected')
  const canShift = Boolean(shiftVerse(onAirDisplay?.reference, 1))
  const selectedAudioDevice = audioDevices.find((device) => device.deviceId === selectedAudioDeviceId)

  const renderCard = (item, accent) => {
    const pendingIdx = pendingItems.findIndex((p) => p.queueId === item.queueId)
    const isKeyboardActive = pendingIdx === selectedQueueIndex
    const confidencePct = item.confidence
      ? Math.round(item.confidence <= 1 ? item.confidence * 100 : item.confidence)
      : null

    const isLoading = projectingIds.has(item.queueId)
    const isFlipping = flippingIds.has(item.queueId)
    const isFailed = failedIds.has(item.queueId)
    const isProjected = item.status === 'projected' || item.reference === onAir?.reference
    const prevRef = shiftVerse(item.reference, -1)
    const nextRef = shiftVerse(item.reference, 1)

    return (
      <article
        key={item.queueId}
        className={`live-card ${accent === 'ai' ? 'is-ai' : ''} ${isKeyboardActive ? 'is-keyboard-active' : ''} ${isProjected ? 'is-projected ring-2 ring-emerald-500/70 shadow-lg shadow-emerald-500/20' : ''} ${isLoading ? 'is-loading' : ''} ${isFailed ? 'is-failed' : ''} ${isFlipping ? 'is-flipping' : ''}`}
        onClick={() => setSelectedQueueIndex(pendingIdx)}
      >
        <div className="live-card-head">
          <div className="flex items-center gap-2">
            <span className="live-card-ref">{item.reference}</span>
            <button
              onClick={(e) => { e.stopPropagation(); setChapterModalRef(item.reference) }}
              className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-3 hover:bg-accent/20 text-accent transition-all"
              title="Ouvrir tout le chapitre"
            >
              📖 Chapitre
            </button>
          </div>
          <span className={`live-card-badge ${accent === 'ai' ? 'is-ai bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold' : 'is-local'} ${isProjected ? 'is-projected-badge' : ''}`}>
            {isProjected ? 'À l\'antenne' : (accent === 'ai' ? `Paraphrase (${confidencePct ?? 95}%)` : 'Match Exact')}
          </span>
        </div>

        {/* Jauge de confiance */}
        {!isProjected && confidencePct != null && (
          <div
            className={`live-card-gauge ${confidencePct >= 95 ? 'is-sure' : confidencePct >= 80 ? 'is-likely' : 'is-doubtful'}`}
            role="meter"
            aria-valuenow={confidencePct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Confiance de la détection : ${confidencePct} %`}
          >
            <span style={{ width: `${Math.max(4, Math.min(100, confidencePct))}%` }} />
          </div>
        )}

        <p
          className="live-card-text leading-relaxed"
        >
          {renderHighlightedVerseText(item.text, item.detectedFrom || currentTranscript, accent === 'ai')}
        </p>

        {/* Quick Verse Navigation & Direct Jump Selector */}
        <div className="flex flex-col gap-1.5 my-1.5 pt-1.5 border-t border-white/5">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
            {prevRef && (
              <button
                type="button"
                className="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-3 hover:bg-surface-2 text-text-dim hover:text-white flex-shrink-0"
                onClick={(e) => { e.stopPropagation(); isProjected ? sendReference(prevRef) : handleAdjacentVerse(item, prevRef) }}
                title={isProjected ? `Afficher ${prevRef} à l'antenne` : `Remplacer la carte par ${prevRef}`}
              >
                ◄ {prevRef.split(' ').pop()}
              </button>
            )}
            {/* Quick jump targets: 5, 10, 15, 20, 25, 30 */}
            {(() => {
              const match = /^(.+?)\s+(\d+):(\d+)/.exec(item.reference || '')
              if (!match) return null
              const bookChap = `${match[1]} ${match[2]}`
              const currV = parseInt(match[3], 10)
              const jumpTargets = [1, 5, 10, 15, 20, 25, 30, 40].filter((v) => v !== currV)

              return (
                <div className="flex items-center gap-1 overflow-x-auto flex-1">
                  <span className="text-[9px] text-text-faint uppercase font-bold mr-1">Saut:</span>
                  {jumpTargets.map((targetV) => (
                    <button
                      key={targetV}
                      className="px-1.5 py-0.5 rounded text-[9.5px] font-mono bg-accent/10 hover:bg-accent/30 text-accent font-semibold flex-shrink-0 transition-all"
                      onClick={(e) => {
                        e.stopPropagation()
                        const targetRef = `${bookChap}:${targetV}`
                        if (isProjected) {
                          sendReference(targetRef)
                        } else {
                          prepareReference(targetRef)
                        }
                      }}
                      title={`Sauter directement au verset ${targetV}`}
                    >
                      v.{targetV}
                    </button>
                  ))}
                </div>
              )
            })()}
            {nextRef && (
              <button
                type="button"
                className="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-3 hover:bg-surface-2 text-text-dim hover:text-white flex-shrink-0"
                onClick={(e) => { e.stopPropagation(); isProjected ? sendReference(nextRef) : handleAdjacentVerse(item, nextRef) }}
                title={isProjected ? `Afficher ${nextRef} à l'antenne` : `Remplacer la carte par ${nextRef}`}
              >
                {nextRef.split(' ').pop()} ►
              </button>
            )}
          </div>

        </div>

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
            
            {!isProjected && (
              <button
                className="vp-btn vp-btn--ghost vp-btn--sm"
                onClick={(e) => { e.stopPropagation(); previewReference(item.reference) }}
                disabled={isLoading || previewBusy}
                title={`Monter ${item.reference} en préparation, sans l'envoyer [ P ]`}
              >
                Préparer
              </button>
            )}

            {isProjected ? (
              <button
                className="vp-btn vp-btn--sm vp-btn--ok shadow-emerald-500/20 shadow-md"
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
      {followModalOpen && (
        <FollowModal isOpen={followModalOpen} onClose={() => setFollowModalOpen(false)} />
      )}
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
              <button
                className="vp-btn"
                onClick={() => runPreflight({ probeCloud: true, requireMicro: true })}
                disabled={preflightLoading}
              >
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
      {(visibleRejection || micError || micSilent) && (
        <div className="live-status-alerts flex gap-4 items-center px-4 py-2 bg-surface-1 border border-border-weak rounded-xl animate-fade-in">
          {/* Un micro ouvert sur une entrée sans signal ressemblait, à l'écran,
              à un micro qui attend qu'on parle. Ici on le nomme. */}
          {micSilent && (
            <span className="live-ai-note is-error">
              Micro ouvert mais AUCUN signal depuis 8 s
              {selectedAudioDevice?.label ? ` sur « ${selectedAudioDevice.label} »` : ''} — changez la source audio dans Paramètres → Audio.
            </span>
          )}
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

            {/* Contrôle micro. Le halo suit l'amplitude réelle : il dit à
                l'opérateur, d'un seul regard et sans lire un chiffre, que le
                micro entend quelque chose. C'est de l'état, pas du décor —
                d'où l'absence d'animation quand le micro est à l'arrêt. */}
            <div className="flex flex-col gap-2">
              <button
                className={`vp-btn ${isListening ? 'vp-btn--ghost' : 'vp-btn--primary'} w-full py-1.5 mic-button ${isListening ? 'is-live' : ''}`}
                style={isListening ? { '--mic-level': Math.min(1, volume / 100) } : undefined}
                onClick={handleToggleListening}
              >
                {isListening ? 'Arrêter Micro' : 'Démarrer Micro'}
              </button>
              
              <div className="text-[10px] text-[var(--text-dim)] truncate mt-1">
                {selectedAudioDevice?.label || 'Entrée par défaut du système'}
              </div>
            </div>
          </div>

          {/* Arrêt d'urgence — le seul geste qui doit rester sous la main sans
              qu'on le cherche. */}
          <button className="vp-btn vp-btn--danger vp-btn--sm w-full flex-shrink-0" onClick={handlePanic}>
            Arrêt d'urgence
          </button>

          {/* Ouvrir un écran, lancer le contrôle avant direct, régler l'audio :
              trois gestes d'AVANT le culte, faits une fois. Ils occupaient en
              permanence la moitié de la colonne, au détriment de la file de
              détection — qui, elle, sert toute la prédication. Ils sont ici,
              repliés. */}
          <details className="live-outils flex-shrink-0">
            <summary>
              <span className="vp-label">Avant le culte</span>
              <span className={`vp-chip ${sundaySafeMode || shadowMode ? 'is-ok' : 'is-warn'}`}>
                {shadowMode ? 'Ombre' : sundaySafeMode ? 'Mode sûr' : 'Auto autorisé'}
              </span>
              {/* Le plan de prédication renforce la détection en silence : il
                  départage deux versets que le micro confond. Sans ce compteur,
                  rien ne distingue « le moteur s'appuie sur douze références »
                  de « il n'en connaît aucune » — et l'écart est grand. */}
              {planCount ? (
                <span
                  className="vp-chip is-ok"
                  title={`Le moteur attend ${planCount} référence(s) du plan de prédication et s'en sert pour départager les versets mal entendus.`}
                >
                  Plan · {planCount}
                </span>
              ) : null}
            </summary>
            <div className="live-outils-corps">
              <button className="vp-btn vp-btn--sm w-full" onClick={() => { runPreflight(); setPreflightOpen(true) }}>
                Contrôle avant direct
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full flex items-center justify-center gap-1.5 text-sky-400 font-medium hover:bg-sky-950/30" onClick={() => setFollowModalOpen(true)}>
                📱 QR Code Mobile (/follow)
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full" onClick={openProjectionWindow}>
                Écran Secours
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full" onClick={openStageWindow}>
                Moniteur Scène
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full" onClick={openObsWindow}>
                Source OBS/vMix
              </button>
              <button className="vp-btn vp-btn--ghost vp-btn--sm w-full" onClick={() => setActiveTab('settings')}>
                Paramètres audio et moteurs
              </button>
            </div>
          </details>

          {/* ── DÉROULÉ DU CULTE ──
              Il traversait toute la largeur sous les trois colonnes, pour une
              liste de références qui tient dans une colonne étroite. Il occupe
              maintenant la place laissée libre à gauche, et la file de détection
              récupère la hauteur. */}
          <div className="cult-timeline-panel">
            <div className="cult-timeline-head">
              <span className="cult-timeline-title">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
                </svg>
                Déroulé du culte
                {preparedVerses.length > 0 && <span className="count">{preparedVerses.length}</span>}
              </span>
              {preparedVerses.length > 0 && (
                <button className="vp-btn vp-btn--ghost vp-btn--sm cult-timeline-clear" onClick={clearPreparedVerses} title="Effacer uniquement le déroulé préparé">
                  Effacer le déroulé
                </button>
              )}
            </div>
            <div className="cult-timeline-scroll">
              {preparedVerses.length === 0 && projectedHistory.length === 0 ? (
                <span className="text-xs text-[var(--text-faint)] italic">Aucun verset préparé. Saisissez une référence puis validez avec Entrée.</span>
              ) : (
                <>
                  {preparedVerses.length > 0 && <span className="cult-timeline-section">Préparés</span>}
                  {preparedVerses.map((item, idx) => {
                    const isCurrent = onAirDisplay?.reference === item.reference
                    const isLoading = projectingIds.has(item.id)
                    return (
                      <div
                        key={item.id}
                        className={`cult-timeline-item is-prepared ${isCurrent ? 'is-current' : ''} ${isLoading ? 'is-loading' : ''}`}
                      >
                        <button
                          className="cult-timeline-project"
                          onClick={() => handleProjectPrepared(item)}
                          disabled={isLoading}
                          title={`Projeter ${item.reference}`}
                        >
                          <span className="cult-timeline-order">{idx + 1}</span>
                          <span className="cult-timeline-ref">{item.reference}</span>
                          <span className="cult-timeline-state">
                            {isLoading ? 'Envoi…' : isCurrent ? 'À l’antenne' : item.lastProjectedAt ? 'Déjà projeté' : 'Prêt'}
                          </span>
                        </button>
                        <button
                          className="cult-timeline-remove"
                          onClick={() => removePreparedVerse(item.id)}
                          aria-label={`Retirer ${item.reference} du déroulé`}
                          title="Retirer du déroulé"
                        >
                          ×
                        </button>
                      </div>
                    )
                  })}

                  {projectedHistory.length > 0 && <span className="cult-timeline-section">Historique</span>}
                  {projectedHistory.map((item, idx) => {
                    const isCurrent = onAirDisplay?.reference === item.reference
                    const timeStr = item.detectedAt
                      ? new Date(item.detectedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
                      : '10:00'
                    return (
                      <button
                        key={item.queueId || idx}
                        className={`cult-timeline-item ${isCurrent ? 'is-current' : ''}`}
                        onClick={() => handleProjectFromQueue(item.queueId, item.reference, item.text)}
                        title="Cliquer pour reprojeter à l'antenne"
                      >
                        <span className="cult-timeline-time">{timeStr}</span>
                        <span className="cult-timeline-ref">{item.reference}</span>
                      </button>
                    )
                  })}
                </>
              )}
            </div>
          </div>
        </div>

        {/* ── COLONNE CENTRALE : FILE DE VALIDATION LARGE ── */}
        <div className="live-col-center">
          <section className="vp-panel live-queue flex-1 flex flex-col min-height-0 overflow-hidden">
            <div className="live-queue-head flex-shrink-0">
              <div className="flex items-center gap-3">
                <h2>À valider <span className="count">{pendingItems.length}</span></h2>
                {/* Densité : quand le prédicateur enchaîne, quatre cartes
                    remplissent la colonne et le reste passe sous la ligne de
                    flottaison — au moment précis où il ne faut pas chercher. */}
                <button
                  type="button"
                  className={`live-densite text-[10px] px-2 py-0.5 font-semibold rounded transition-all ${
                    fileCompacte ? 'bg-sky-600/20 text-sky-300' : 'bg-surface-3 text-text-dim hover:bg-surface-2'
                  }`}
                  onClick={basculerDensite}
                  aria-pressed={fileCompacte}
                  title={fileCompacte
                    ? 'Affichage compact : plus de versets à l’écran. Cliquez pour revenir aux cartes détaillées.'
                    : 'Cartes détaillées. Cliquez pour resserrer et voir plus de versets à la fois.'}
                >
                  {fileCompacte ? '☰ compact' : '▤ détaillé'}
                </button>
                
                {/* Triggers: Auto-Scroll & Diffusion en direct */}
                <div className="flex items-center gap-4 text-xs font-semibold text-[var(--text-dim)]">
                  <label className="flex items-center gap-2 cursor-pointer" title="Défilement automatique vers le dernier verset">
                    <button
                      className={`vp-switch ${autoScroll ? 'is-on' : ''}`}
                      onClick={() => setAutoScroll(!autoScroll)}
                      role="switch"
                      aria-checked={autoScroll}
                    >
                      <span className="vp-switch-thumb" />
                    </button>
                    Auto-Scroll
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer" title="Projeter automatiquement les versets fiables sans validation manuelle">
                    <button
                      className={`vp-switch ${autoSend ? 'is-on' : ''}`}
                      onClick={() => setAutoSend(!autoSend)}
                      role="switch"
                      aria-checked={autoSend}
                    >
                      <span className="vp-switch-thumb" />
                    </button>
                    Diffusion en direct
                  </label>
                </div>
              </div>

              <div className="live-queue-tools">
                <span className="live-queue-hints">
                  <span className="vp-kbd">↑↓</span> naviguer
                  <span className="vp-kbd">Espace</span> projeter
                  <span className="vp-kbd">Échap</span> ignorer
                  <span className="vp-kbd">/</span> recherche
                </span>
                {projectionQueue.length > 0 && (
                  <button className="vp-btn vp-btn--ghost vp-btn--sm" onClick={clearDetectedVerses} title="Effacer uniquement les versets détectés, sans toucher au déroulé">
                    Vider les détections
                  </button>
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

            <div ref={queueScrollRef} className={`live-queue-scroll flex-1 overflow-y-auto pr-1 ${fileCompacte ? 'is-compact' : ''}`}>
              {displayQueue.length === 0 ? (
                <div className="live-empty">
                  <strong>Aucun verset en attente</strong>
                  <p>Démarrez le micro : les références citées pendant la prédication apparaîtront ici pour validation.</p>
                </div>
              ) : (
                <>
                  {displayQueue.map((item) => {
                    const isSemantic = isSemanticSuggestion(item)
                    const isDone = item.status !== 'pending'
                    const accent = isDone ? 'done' : (isSemantic ? 'ai' : 'local')
                    return renderCard(item, accent)
                  })}
                </>
              )}
            </div>
            
            {/* Ce que fait la touche Entrée est désormais un RÉGLAGE, affiché
                à côté du champ. Une régie qui projette sur Entrée va vite ;
                une régie qui prépare ne se trompe jamais devant l'assemblée.
                Les deux se défendent — ce qui ne se défendait pas, c'était de
                ne pas savoir laquelle était active. */}
            <div ref={manualBarRef} className="live-manual-bar relative mt-3 pt-3 border-t border-border-weak flex-shrink-0 flex flex-col gap-2">
              {showManualSuggestions && manualSuggestions.length > 0 && (
                <div
                  className="absolute bottom-full mb-2 left-0 right-0 max-h-[340px] overflow-y-auto bg-surface-raised border border-border-strong rounded-card shadow-elev-4 z-50 p-1.5 animate-slide-in backdrop-blur-md"
                  role="listbox"
                >
                  <div className="px-2.5 py-1.5 text-[10.5px] font-mono text-text-faint flex items-center justify-between border-b border-border mb-1">
                    <span>{manualSuggestions.length} proposition{manualSuggestions.length > 1 ? 's' : ''} trouvée{manualSuggestions.length > 1 ? 's' : ''}</span>
                    <span>↑↓ naviguer · Entrée projeter · Échap fermer</span>
                  </div>
                  {manualSuggestions.map((result, idx) => {
                    const isActive = idx === manualActiveIndex
                    const methodLabel = METHOD_LABELS[result.detection_method] || result.detection_method || 'Proposition'
                    return (
                      <div
                        key={`${result.reference}-${idx}`}
                        className={`block w-full text-left rounded-input p-2.5 cursor-pointer transition-colors duration-150 ${
                          isActive ? 'bg-sky-950/60 border border-sky-500/40 text-white' : 'hover:bg-surface-elevated text-text-primary'
                        }`}
                        onMouseEnter={() => setManualActiveIndex(idx)}
                        onClick={() => {
                          sendReference(result.reference)
                          setManualReference('')
                          setShowManualSuggestions(false)
                        }}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <strong className="text-[13.5px] font-semibold text-text-primary">
                            {result.reference}
                          </strong>
                          <div className="flex items-center gap-1.5">
                            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                              result.source === 'ai' || result.detection_method?.includes('ai')
                                ? 'bg-amber-500/20 text-amber-300 font-semibold'
                                : 'bg-surface-elevated text-text-dim'
                            }`}>
                              {methodLabel}
                              {result.matched_version ? ` · ${result.matched_version}` : ''}
                              {result.confidence ? ` · ${Math.round(result.confidence * 100)} %` : ''}
                            </span>
                            <button
                              type="button"
                              className="px-2 py-0.5 text-[10.5px] font-semibold rounded bg-sky-600 hover:bg-sky-500 text-white transition-colors ml-1"
                              onClick={(e) => {
                                e.stopPropagation()
                                sendReference(result.reference)
                                setManualReference('')
                                setShowManualSuggestions(false)
                              }}
                              title="Projeter immédiatement à l'écran"
                            >
                              Projeter
                            </button>
                            <button
                              type="button"
                              className="px-2 py-0.5 text-[10.5px] rounded bg-surface-3 hover:bg-surface-2 text-text-dim hover:text-white transition-colors"
                              onClick={(e) => {
                                e.stopPropagation()
                                previewReference(result.reference)
                                setManualReference('')
                                setShowManualSuggestions(false)
                              }}
                              title="Monter en préparation"
                            >
                              Préparer
                            </button>
                          </div>
                        </div>
                        <p className="mt-1 text-[12px] leading-snug text-text-secondary line-clamp-2">
                          {result.matched_text || result.text || ''}
                        </p>
                      </div>
                    )
                  })}
                </div>
              )}

              <div className="live-manual-actions">
                <input
                  ref={manualInputRef}
                  className="vp-input flex-1 py-1.5 text-sm"
                  type="text"
                  value={manualReference}
                  onChange={(e) => handleManualInputChange(e.target.value)}
                  onFocus={() => {
                    if (manualSuggestions.length > 0 && manualReference.trim().length >= 2) {
                      setShowManualSuggestions(true)
                    }
                  }}
                  placeholder="Saisir un verset (ex : Jn 3:16, Romains 8:28…)"
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      e.preventDefault()
                      setShowManualSuggestions(false)
                    } else if (e.key === 'ArrowDown' && showManualSuggestions && manualSuggestions.length > 0) {
                      e.preventDefault()
                      setManualActiveIndex((i) => Math.min(manualSuggestions.length - 1, i + 1))
                    } else if (e.key === 'ArrowUp' && showManualSuggestions && manualSuggestions.length > 0) {
                      e.preventDefault()
                      setManualActiveIndex((i) => Math.max(0, i - 1))
                    } else if (e.key === 'Enter') {
                      e.preventDefault()
                      if (showManualSuggestions && manualSuggestions.length > 0 && manualSuggestions[manualActiveIndex]) {
                        const sel = manualSuggestions[manualActiveIndex]
                        sendReference(sel.reference)
                        setManualReference('')
                        setShowManualSuggestions(false)
                      } else {
                        handleSendManual()
                      }
                    }
                  }}
                />
                <button
                  className="vp-btn vp-btn--primary px-4 text-xs font-semibold"
                  onClick={handleSendManual}
                  disabled={!manualReference.trim()}
                >
                  Projeter
                </button>
                <button
                  className="vp-btn vp-btn--ghost px-3 text-xs"
                  onClick={() => { previewReference(manualReference.trim()); setManualReference(''); setShowManualSuggestions(false) }}
                  disabled={!manualReference.trim() || previewBusy}
                  title="Monter en préparation, sans rien envoyer à la salle"
                >
                  Préparer
                </button>
              </div>
              {/* Dix versets autour de celui qui est à l'antenne. Le régisseur
                  qui doit suivre un prédicateur qui recule de trois versets ne
                  devrait pas avoir à retaper une référence. */}
              {versetsVoisins && (
                <div className="live-quick-row flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
                  <span className="text-[10px] text-text-faint font-semibold uppercase whitespace-nowrap mr-1">
                    {onAirNavChips.bookName} {onAirNavChips.chapNum} :
                  </span>
                  {versetsVoisins.numeros.map((v) => (
                    <button
                      key={v}
                      className={`live-quick-chip text-[10.5px] px-2 py-0.5 font-medium flex-shrink-0 transition-all ${
                        v < versetsVoisins.courant
                          ? 'bg-surface-3 text-text-dim hover:bg-surface-2 hover:text-white'
                          : 'bg-surface-2 text-text-dim hover:bg-sky-600 hover:text-white'
                      }`}
                      title={`Projeter ${onAirNavChips.bookName} ${onAirNavChips.chapNum}:${v}`}
                      onClick={() => sendReference(`${onAirNavChips.bookName} ${onAirNavChips.chapNum}:${v}`)}
                    >
                      {v}
                    </button>
                  ))}
                  <span className="text-[10px] text-text-faint whitespace-nowrap ml-1 flex-shrink-0">
                    / {versetsVoisins.total}
                  </span>
                </div>
              )}
              <div className="live-quick-row flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
                {onAirNavChips ? (
                  <>
                    <span className="text-[10px] text-text-faint font-semibold uppercase whitespace-nowrap mr-1">
                      Direct ({onAirNavChips.bookName}) :
                    </span>
                    {onAirNavChips.prevC && (
                      <button
                        className="live-quick-chip text-[10.5px] px-2 py-0.5 font-medium bg-surface-3 hover:bg-surface-2 text-text-dim hover:text-white transition-all flex-shrink-0"
                        onClick={() => sendReference(onAirNavChips.prevC.ref)}
                        title={`Projeter le chapitre précédent ${onAirNavChips.prevC.ref}`}
                      >
                        {onAirNavChips.prevC.label}
                      </button>
                    )}
                    {onAirNavChips.prevV && (
                      <button
                        className="live-quick-chip text-[10.5px] px-2.5 py-0.5 font-bold bg-accent/20 hover:bg-accent/40 text-accent border border-accent/30 transition-all flex-shrink-0"
                        onClick={() => sendReference(onAirNavChips.prevV.ref)}
                        title={`Projeter immédiatement ${onAirNavChips.prevV.ref}`}
                      >
                        {onAirNavChips.prevV.label}
                      </button>
                    )}
                    {onAirNavChips.nextV && (
                      <button
                        className="live-quick-chip text-[10.5px] px-2.5 py-0.5 font-bold bg-accent/20 hover:bg-accent/40 text-accent border border-accent/30 transition-all flex-shrink-0"
                        onClick={() => sendReference(onAirNavChips.nextV.ref)}
                        title={`Projeter immédiatement ${onAirNavChips.nextV.ref}`}
                      >
                        {onAirNavChips.nextV.label}
                      </button>
                    )}
                    {onAirNavChips.nextC && (
                      <button
                        className="live-quick-chip text-[10.5px] px-2 py-0.5 font-medium bg-surface-3 hover:bg-surface-2 text-text-dim hover:text-white transition-all flex-shrink-0"
                        onClick={() => sendReference(onAirNavChips.nextC.ref)}
                        title={`Projeter le chapitre suivant ${onAirNavChips.nextC.ref}`}
                      >
                        {onAirNavChips.nextC.label}
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    <span className="text-[10px] text-text-faint font-semibold uppercase whitespace-nowrap mr-1">Raccourcis :</span>
                    {quickRefs.map((sug) => (
                      <button key={sug.ref} className="live-quick-chip text-[10px] px-2 py-0.5" onClick={() => prepareReference(sug.ref)} title={`Ajouter ${sug.ref} au déroulé`}>
                        {sug.label}
                      </button>
                    ))}
                  </>
                )}
              </div>
            </div>
          </section>
        </div>

        {/* ── COLONNE DROITE : PRÉPARATION, ANTENNE, JOURNAL ── */}
        <div className="live-col-right">
          {/* ── PRÉPARATION (preview) ──
              Ce panneau ne touche aucun écran de salle. Il montre ce que
              l'assemblée verra APRÈS l'envoi — le seul moment où un verset mal
              coupé peut encore être rattrapé. */}
          <section className="vp-panel live-preview flex-shrink-0">
            <div className="live-preview-head">
              <span className={`live-preview-badge ${previewSlide ? 'is-armed' : ''}`}>
                <span className="dot" />Préparation
              </span>
              {previewSlide && (
                <button
                  className="vp-btn vp-btn--ghost vp-btn--sm py-0.5 px-2 text-[10px]"
                  onClick={clearPreview}
                  title="Vider la préparation (n'affecte pas l'antenne)"
                >
                  Vider
                </button>
              )}
            </div>

            {previewSlide ? (
              <>
                <div className="flex items-center justify-between gap-2">
                  <div className="live-preview-ref font-bold">{previewSlide.reference}</div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                    {previewSlide.version}
                  </span>
                </div>

                {/* Seul le PREMIER verset part à l'écran ; les suivants sont là
                    pour vérifier le découpage. Les déplier coûterait la hauteur
                    dont le journal de transcription a besoin — ils restent donc
                    repliés, sous un compteur qui dit ce qui suit. */}
                {previewSlide.verses?.length > 1 ? (
                  <div className="live-preview-verses">
                    <p className="live-preview-verse">
                      <span className="live-preview-verse-n">{previewSlide.verses[0].n}</span>
                      {previewSlide.verses[0].text}
                    </p>
                    <button
                      type="button"
                      className="live-preview-count"
                      onClick={() => setPreviewDeplie((v) => !v)}
                      aria-expanded={previewDeplie}
                    >
                      {previewDeplie ? '▲ Replier' : `▼ ${previewSlide.verses.length - 1} verset${previewSlide.verses.length > 2 ? 's' : ''} à suivre`}
                    </button>
                    {previewDeplie && (
                      <div className="live-preview-suite">
                        {previewSlide.verses.slice(1).map((v) => (
                          <p key={v.n} className="live-preview-verse">
                            <span className="live-preview-verse-n">{v.n}</span>{v.text}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="live-preview-text">{previewSlide.text || 'Texte non chargé.'}</p>
                )}

                <button
                  className="live-preview-take"
                  onClick={takePreview}
                  disabled={previewBusy}
                  title="Envoyer la préparation à l'antenne [ T ]"
                >
                  {previewBusy ? 'Envoi…' : 'Envoyer à l’antenne'}
                  <span className="vp-kbd">T</span>
                </button>
              </>
            ) : (
              <div className="live-preview-empty">
                <strong>Rien en préparation</strong>
                <p>
                  <span className="vp-kbd">P</span> sur une détection, ou « Préparer » sous la
                  saisie manuelle. L'assemblée ne verra rien avant l'envoi.
                </p>
              </div>
            )}
          </section>

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
            {/* La clé change avec la référence : l'élément se remonte et rejoue
                l'animation d'arrivée. L'œil voit que quelque chose vient de
                prendre l'antenne, sans avoir à relire le texte. */}
            <div key={onAirDisplay?.reference || 'vide'} className="flex items-center justify-between">
              <div className="live-onair-ref font-bold text-lg">
                {onAirDisplay?.reference || '—'}
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold">
                {onAirDisplay?.version || activeBible || 'LSG'}
              </span>
            </div>

            {/* BARRE DE PILLS DE VERSIONS DANS LE HEADER (Accès 1-Clic) */}
            {onAirDisplay?.reference && (
              <div className="flex items-center gap-1 overflow-x-auto py-1.5 my-1 border-y border-white/5">
                {/* Les versions RÉELLEMENT chargées, pas une liste écrite en
                    dur. Les six pastilles existaient sur le poste de
                    développement, où les six fichiers sont présents ; le paquet
                    installé n'en embarque que deux. Chez l'église, le pasteur
                    demandait la Semeur, l'opérateur cliquait « SEM », et
                    l'écran ne bougeait pas. */}
                {availableBibles.map((ver) => {
                  const currentVer = onAirDisplay?.version || activeBible || 'LSG'
                  const isActive = currentVer === ver
                  return (
                    <button
                      key={ver}
                      onClick={() => handleSwitchVersion(ver)}
                      className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium transition-all ${
                        isActive
                          ? 'bg-sky-500 text-white font-bold shadow-sm'
                          : 'bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-700'
                      }`}
                      title={`Basculer vers ${BIBLE_NAMES[ver] || ver}`}
                    >
                      {ver} {isActive ? '★' : ''}
                    </button>
                  )
                })}
              </div>
            )}

            {/* SUGGESTION VOCALE ASR (NON-AUTOMATIQUE) */}
            {voiceSuggestedVersion && onAirDisplay?.reference && (
              <div className="flex items-center justify-between p-2 my-2 bg-sky-500/10 border border-sky-500/30 rounded-xl text-xs animate-in fade-in">
                <span className="text-sky-300 font-medium flex items-center gap-1.5">
                  🎙️ Le pasteur a demandé : <strong className="text-white">{BIBLE_NAMES[voiceSuggestedVersion]} ({voiceSuggestedVersion})</strong>
                </span>
                <button
                  onClick={() => handleSwitchVersion(voiceSuggestedVersion)}
                  className="px-2.5 py-1 rounded bg-sky-500 text-slate-950 font-bold text-[11px] hover:bg-sky-400 transition-all"
                >
                  Appliquer [ ESPACE ]
                </button>
              </div>
            )}

            <p
              className="live-onair-text select-text cursor-text"
              tabIndex={0}
              aria-label="Texte du verset projeté. Sélectionnez les mots à annoter."
              onMouseUp={(event) => handleTextSelection(event, onAirSelectionKey)}
              title={onAirDisplay ? 'Sélectionnez directement les mots à surligner, souligner ou entourer' : undefined}
            >
              {onAirDisplay?.text
                ? renderSelectedVerseText(onAirDisplay.text, onAirSelectedText)
                : 'Aucun verset projeté.'}
            </p>

            <div className={`live-annotation-toolbar live-annotation-toolbar--onair ${onAirDisplay ? '' : 'is-unavailable'}`}>
              <span className="live-annotation-heading">
                <LiveHighlightIcon type="highlight" size={15} />
                <span>Surlignage Live</span>
              </span>
              <span className={`live-annotation-selection ${onAirSelectedText ? 'has-selection' : ''}`} title={onAirSelectedText || undefined}>
                {onAirSelectedText
                  ? `Sélection : « ${onAirSelectedText} »`
                  : onAirDisplay
                    ? 'Sélectionnez des mots dans le verset ci-dessus'
                    : 'Projetez d’abord un verset'}
              </span>
              <div className="live-annotation-actions" role="group" aria-label="Annoter la sélection à l'antenne">
                <button
                  type="button"
                  className="live-annotation-button is-highlight"
                  disabled={!onAirSelectedText || annotationBusy}
                  aria-label="Surligner la sélection en jaune"
                  title={!onAirSelectedText ? 'Sélectionnez d’abord des mots dans le verset' : 'Surligner la sélection'}
                  onClick={() => sendLiveAnnotation('highlight')}
                >
                  <LiveHighlightIcon type="highlight" />
                  <span>Surligner</span>
                </button>
                <button
                  type="button"
                  className="live-annotation-button is-underline"
                  disabled={!onAirSelectedText || annotationBusy}
                  aria-label="Souligner la sélection en rouge"
                  title={!onAirSelectedText ? 'Sélectionnez d’abord des mots dans le verset' : 'Souligner la sélection'}
                  onClick={() => sendLiveAnnotation('underline')}
                >
                  <LiveHighlightIcon type="underline" />
                  <span>Souligner</span>
                </button>
                <button
                  type="button"
                  className="live-annotation-button is-circle"
                  disabled={!onAirSelectedText || annotationBusy}
                  aria-label="Entourer la sélection en bleu"
                  title={!onAirSelectedText ? 'Sélectionnez d’abord des mots dans le verset' : 'Entourer la sélection'}
                  onClick={() => sendLiveAnnotation('circle')}
                >
                  <LiveHighlightIcon type="circle" />
                  <span>Entourer</span>
                </button>
                <button
                  type="button"
                  className="live-annotation-button is-clear"
                  disabled={!onAirDisplay || annotationBusy}
                  aria-label="Effacer les annotations à l'antenne"
                  title="Effacer les annotations à l'antenne"
                  onClick={() => sendLiveAnnotation('clear')}
                >
                  <LiveHighlightIcon type="clear" />
                  <span>{annotationBusy ? 'Envoi…' : 'Effacer'}</span>
                </button>
              </div>
            </div>
            
            {followMode && followProgress && (
              <div className="live-follow-bar mb-3" aria-label="Progression de la lecture">
                <div style={{ width: `${Math.round(followProgress.ratio * 100)}%` }} />
              </div>
            )}
            
            {/* BOUTON COMPARER LES VERSIONS (APERÇU MULTI-VERSION) */}
            {onAirDisplay?.reference && (
              <div className="mb-2">
                <button
                  onClick={() => toggleCompareMode(onAirDisplay.reference)}
                  className="w-full py-1 px-2.5 rounded-lg bg-slate-800/60 border border-white/5 text-xs text-slate-300 hover:text-white hover:bg-slate-800 transition-all flex items-center justify-between"
                >
                  <span>Comparer les versions</span>
                  <span className="text-[10px] font-mono opacity-70">{compareOpen ? '▲ Masquer' : '▼ Aperçu'}</span>
                </button>

                {compareOpen && comparePreviews && (
                  <div className="mt-2 space-y-1.5 p-2 rounded-xl bg-slate-950/80 border border-white/10 max-h-48 overflow-y-auto">
                    {Object.entries(comparePreviews).map(([ver, text]) => (
                      <div
                        key={ver}
                        onClick={() => handleSwitchVersion(ver)}
                        className={`p-2 rounded-lg text-xs cursor-pointer border transition-all ${
                          (onAirDisplay?.version || activeBible) === ver
                            ? 'bg-sky-500/10 border-sky-500/40 text-sky-200'
                            : 'bg-slate-900/60 border-white/5 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        <div className="flex items-center justify-between font-mono font-bold text-[10px] text-sky-400 mb-0.5">
                          <span>{ver} — {BIBLE_NAMES[ver] || ver}</span>
                          {(onAirDisplay?.version || activeBible) === ver && <span>★ À l'antenne</span>}
                        </div>
                        <p className="line-clamp-2 text-[11px] leading-relaxed text-slate-300">{text}</p>
                      </div>
                    ))}
                  </div>
                )}
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
                disabled={!canShift || sundaySafeMode}
                aria-pressed={followMode}
                title={sundaySafeMode
                  ? 'Indisponible en mode sûr : chaque projection exige une validation'
                  : followMode
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

            {/* Son difficile : le logiciel se dégrade au lieu de deviner. Sans
                ce bandeau, l'opérateur voit VersePro devenir muet et le croit
                en panne — alors qu'il fait exactement ce qu'il doit. */}

            
            {/* Texte brut, pas un <span> par mot : le découpage reconstruisait
                des dizaines de nœuds à chaque partiel, avec des clés d'index
                que React ne peut pas réutiliser quand la phrase s'allonge.
                Rien ici ne cible les mots un à un — la lecture vivante mot à
                mot, elle, vit sur l'écran de projection, qui a son propre
                rendu. */}
            <div className="live-transcript-scroll" id="live-transcript-scroll">
              {currentTranscript ? (
                <p className="whitespace-pre-wrap">{currentTranscript}</p>
              ) : (
                <div className="text-[var(--text-faint)] italic text-center py-8">
                  {!isListening
                    ? 'Micro arrêté.'
                    : micSilent
                      ? 'Aucun signal sur l’entrée micro. Vérifiez la source audio dans Paramètres → Audio.'
                      : volume > 2
                        ? `${asrMode === 'nemotron' ? 'Nemotron' : asrMode === 'vosk' ? 'Vosk' : 'Le moteur ASR'} reçoit le son — transcription en cours...`
                        : 'Micro actif — en attente de parole...'}
                </div>
              )}
              <div ref={transcriptEndRef} />
            </div>
          </section>
        </div>
      </div>

      {chapterModalRef && (
        <ChapterModal
          reference={chapterModalRef}
          onClose={() => setChapterModalRef(null)}
        />
      )}

      {versionsModalOpen && (
        <BibleVersionsModal
          onClose={() => setVersionsModalOpen(false)}
        />
      )}
    </div>
  )
}
