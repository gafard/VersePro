import { create } from 'zustand'
import { BACKEND_BASE, BACKEND_WS_BASE } from './env.js'
import { MAX_RECONNECT_ATTEMPTS, reconnectDelay, shouldReconnect } from './runtime/reconnect.js'

// Variables non-réactives de module privées pour la capture audio globale
let audioContext = null
let mediaStream = null
let processorNode = null
let connectPromise = null

const PREPARED_VERSES_STORAGE_KEY = 'versepro_prepared_verses'

const readPreparedVerses = () => {
  try {
    const stored = JSON.parse(localStorage.getItem(PREPARED_VERSES_STORAGE_KEY) || '[]')
    if (!Array.isArray(stored)) return []
    return stored
      .filter((item) => item && typeof item.reference === 'string' && item.reference.trim())
      .slice(0, 100)
  } catch {
    return []
  }
}

const persistPreparedVerses = (items) => {
  try {
    localStorage.setItem(PREPARED_VERSES_STORAGE_KEY, JSON.stringify(items.slice(0, 100)))
  } catch {
    /* La régie reste utilisable si le stockage navigateur est indisponible. */
  }
}

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

// Store Zustand pour l'état global
export const useStore = create((set, get) => ({
  // État de connexion
  connected: false,
  audioConnected: false,
  connectionStatus: 'starting', // starting | connected | reconnecting | disconnected
  websocket: null,
  
  // État de détection et ASR
  isListening: false,
  // Jalons du chrono de session : le pied de régie compte la durée du direct.
  listeningStartedAt: null,
  listeningStoppedAt: null,
  volume: 0,
  waveform: Array(64).fill(0),
  audioDevices: [],
  selectedAudioDeviceId: (() => {
    try { return localStorage.getItem('versepro_audio_device_id') || '' } catch { return '' }
  })(),
  audioFilterMode: (() => {
    try { return localStorage.getItem('versepro_audio_filter_mode') || 'off' } catch { return 'off' }
  })(),
  micPermissionState: 'unknown',
  micError: null,
  currentTranscript: '',
  detectedReferences: [],
  asrMode: 'deepgram',
  // Santé de la transcription. `fiable: true` par défaut : tant qu'on n'a
  // rien entendu, il n'y a aucune raison d'alerter.
  santeTranscription: { fiable: true, motsMoyens: 0, message: '' },
  selectedEngine: 'auto',
  aiActive: false, // Disponibilité de l'Agent IA sémantique
  
  // Traduction simultanée
  translationLang: '', // ex: 'en', 'es', 'de' ou '' (désactivé)
  currentTranslation: '', // La traduction courante
  
  // Multi-Traduction
  activeBible: 'LSG',
  availableBibles: ['LSG'],
  
  // Ce qui est actuellement projeté à l'écran (référence + texte), null = écran noir
  onAir: null,

  // Toasts de confirmation d'action
  toasts: [],
  addToast: ({ message, kind = 'success', action = null, duration = 3500 }) => {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    set((state) => ({ toasts: [...state.toasts.slice(-2), { id, message, kind, action }] }))
    setTimeout(() => get().dismissToast(id), action ? 6000 : duration)
    return id
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  // Indicateurs de chargement des listes
  historyLoading: false,
  sessionsLoading: false,
  statsLoading: false,
  // Backend injoignable au chargement initial
  backendUnreachable: false,

  // Restaure la file de validation depuis la session en cours (10 dernières minutes)
  // après un rechargement accidentel de la console en plein culte.
  hydrateQueueFromSession: async () => {
    if (get().projectionQueue.length > 0) return
    try {
      const sessionRes = await fetch(`${BACKEND_BASE}/api/v1/session/current`)
      const { session_id } = await sessionRes.json()
      if (!session_id) return
      const versesRes = await fetch(`${BACKEND_BASE}/api/v1/history/verses?limit=10&session_id=${session_id}`)
      const { verses } = await versesRes.json()
      const cutoff = Date.now() - 10 * 60 * 1000
      const recent = (verses || []).filter((v) => {
        const at = new Date(String(v.detected_at).replace(' ', 'T') + 'Z').getTime()
        return at > cutoff
      })
      if (recent.length === 0) return
      set({
        projectionQueue: recent.map((v) => ({
          queueId: `db_${v.id}`,
          reference: v.reference,
          text: v.text,
          version: v.version,
          detectedAt: new Date(String(v.detected_at).replace(' ', 'T') + 'Z').toISOString(),
          confidence: (v.confidence || 100) / 100,
          source: v.source || 'local',
          detectionMethod: v.source === 'ai' ? 'ai_semantic' : 'restored',
          requiresReview: true,
          status: 'pending'
        }))
      })
      get().addToast({ message: `${recent.length} détection(s) récente(s) restaurée(s)`, kind: 'success' })
    } catch {
      /* silencieux : la restauration est un bonus, pas une fonction critique */
    }
  },

  // Récupère l'état de projection courant (survit au rechargement de la page)
  fetchProjectionState: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/current`)
      if (!response.ok) return
      const data = await response.json()
      // Une référence vide = écran noir ou message d'attente : rien à restaurer
      if (data.reference) {
        set({ onAir: { reference: data.reference, text: data.text || '', at: null } })
      }
      set({ 
        outputTheme: data.theme || 'presentation',
        backendUnreachable: false 
      })
    } catch {
      set({ backendUnreachable: true })
    }
  },

  // ProPresenter & Projection Queue
  propresenterConnected: false,
  autoSend: false,
  autopilotMode: true, // true: envoie direct, false: met en attente dans la file
  projectionQueue: [], // Liste des versets détectés en attente de projection
  preparedVerses: readPreparedVerses(), // Déroulé préparé, conservé entre deux lancements
  settings: null,
  aiFilteringMode: 'strict', // 'strict' ou 'open'
  lastAiRejection: null,

  // vMix & Thème d'affichage (Outputs)
  outputTheme: 'presentation',
  projectionStyle: 'default',
  showBibleVersion: true,
  dualTranslations: 'LSG,KJF',
  vmixEnabled: false,
  vmixHost: '127.0.0.1',
  vmixPort: 8088,
  vmixInputId: 'VerseProTitle',
  
  // Session
  sessionId: null,
  sessionsList: [], // Liste des sessions enregistrées
  activeSessionDetails: null, // Détails de la session en cours de visualisation (transcript, summary)
  
  // Historique
  history: [],
  statistics: null,
  
  // Vosk Status
  voskStatus: { installed: false, downloading: false, model_name: '', model_type: '' },
  asrStatus: null,
  semanticStatus: null,
  preflight: null,
  preflightLoading: false,
  sundaySafeMode: true,
  shadowMode: false,
  
  // Actions
  setConnected: (connected) => set({
    connected,
    connectionStatus: connected ? 'connected' : 'disconnected'
  }),
  
  setWebsocket: (ws) => set({ websocket: ws }),
  
  setIsListening: (isListening) => set({ isListening }),
  
  setCurrentTranscript: (transcript) => set({ currentTranscript: transcript }),
  
  addDetectedReference: (reference) => set((state) => ({
    detectedReferences: [reference, ...state.detectedReferences]
  })),
  
  setPropresenterConnected: (connected) => set({ propresenterConnected: connected }),
  
  setAutopilotMode: async (mode) => {
    // Synchronise autoSend (et autopilotMode) avec le backend pour que la projection auto s'accorde
    await get().setAutoSend(mode)
  },
  
  addToProjectionQueue: (verse) => set((state) => {
    const queueId = `${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
    const wasAutoProjected = Boolean(verse.auto_projected || verse.projection_policy === 'autopilot_projected')
    const newEntry = {
      queueId,
      reference: verse.reference,
      text: verse.text,
      version: verse.version || state.activeBible,
      detectedAt: verse.detected_at || new Date().toISOString(),
      confidence: verse.confidence,
      detectedFrom: verse.detected_from || verse.transcript || '',
      source: verse.source || (['ai_semantic', 'semantic_local'].includes(verse.detection_method) ? 'semantic' : 'local'),
      detectionMethod: verse.detection_method,
      explanation: verse.explanation || '',
      candidateScore: verse.candidate_score ?? null,
      rawModelConfidence: verse.raw_model_confidence ?? null,
      projectionPolicy: verse.projection_policy || (verse.requires_review ? 'manual_review' : 'manual_queue'),
      requiresReview: Boolean(verse.requires_review),
      status: wasAutoProjected ? 'projected' : 'pending' // 'pending' | 'projected' | 'rejected'
    }
    return {
      projectionQueue: [...state.projectionQueue, newEntry]
    }
  }),
  
  projectVerseFromQueue: async (queueId, reference, text) => {
    // La file ne passe à « projeté » qu'après accusé du moteur d'affichage.
    const sent = await get().sendReference(reference)
    if (sent) {
      set((state) => ({
        projectionQueue: state.projectionQueue.map((item) =>
          item.queueId === queueId ? { ...item, status: 'projected' } : item
        )
      }))
    }
    
    return sent
  },
  
  rejectVerseFromQueue: (queueId) => set((state) => ({
    projectionQueue: state.projectionQueue.map((item) => 
      item.queueId === queueId ? { ...item, status: 'rejected' } : item
    )
  })),
  
  clearProjectionQueue: () => {
    const previous = get().projectionQueue
    if (previous.length === 0) return
    set({ projectionQueue: [] })
    get().addToast({
      message: `File vidée (${previous.length} élément${previous.length > 1 ? 's' : ''})`,
      kind: 'success',
      action: { label: 'Annuler', onClick: () => set({ projectionQueue: previous }) }
    })
  },

  prepareReference: async (query) => {
    const requested = String(query || '').trim()
    if (!requested) return null

    try {
      const response = await fetch(
        `${BACKEND_BASE}/api/v1/bible/search?q=${encodeURIComponent(requested)}&limit=1`
      )
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Recherche biblique indisponible')
      }

      const data = await response.json()
      const match = data.results?.[0]
      if (!match?.reference || !match?.text) {
        get().addToast({ message: `Référence introuvable : ${requested}`, kind: 'error' })
        return null
      }

      const existing = get().preparedVerses.find((item) => item.reference === match.reference)
      if (existing) {
        get().addToast({ message: `${match.reference} est déjà dans le déroulé`, kind: 'success' })
        return existing
      }

      const item = {
        id: `prepared_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        reference: match.reference,
        text: match.text,
        version: match.version || get().activeBible,
        addedAt: new Date().toISOString(),
        lastProjectedAt: null
      }
      const next = [...get().preparedVerses, item]
      set({ preparedVerses: next })
      persistPreparedVerses(next)
      get().addToast({ message: `${item.reference} ajouté au déroulé`, kind: 'success' })
      return item
    } catch (error) {
      console.error('Erreur de préparation de référence:', error)
      get().addToast({
        message: error.message || `Impossible d'ajouter ${requested}`,
        kind: 'error'
      })
      return null
    }
  },

  projectPreparedVerse: async (id) => {
    const item = get().preparedVerses.find((verse) => verse.id === id)
    if (!item) return false

    const sent = await get().sendReference(item.reference)
    if (!sent) return false

    const projectedAt = new Date().toISOString()
    const next = get().preparedVerses.map((verse) => (
      verse.id === id ? { ...verse, lastProjectedAt: projectedAt } : verse
    ))
    set({ preparedVerses: next })
    persistPreparedVerses(next)
    return true
  },

  removePreparedVerse: (id) => {
    const previous = get().preparedVerses
    const removed = previous.find((item) => item.id === id)
    if (!removed) return

    const next = previous.filter((item) => item.id !== id)
    set({ preparedVerses: next })
    persistPreparedVerses(next)
    get().addToast({
      message: `${removed.reference} retiré du déroulé`,
      kind: 'success',
      action: {
        label: 'Annuler',
        onClick: () => {
          set({ preparedVerses: previous })
          persistPreparedVerses(previous)
        }
      }
    })
  },

  clearPreparedVerses: () => {
    const previous = get().preparedVerses
    if (previous.length === 0) return

    set({ preparedVerses: [] })
    persistPreparedVerses([])
    get().addToast({
      message: `Déroulé vidé (${previous.length} verset${previous.length > 1 ? 's' : ''})`,
      kind: 'success',
      action: {
        label: 'Annuler',
        onClick: () => {
          set({ preparedVerses: previous })
          persistPreparedVerses(previous)
        }
      }
    })
  },
  
  setAutoSend: async (autoSend) => {
    set({ autoSend, autopilotMode: autoSend })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_send: autoSend })
      })
      if (response.ok) {
        const data = await response.json()
        set({
          settings: data,
          autoSend: Boolean(data.auto_send),
          autopilotMode: Boolean(data.auto_send),
          propresenterConnected: Boolean(data.propresenter_connected)
        })
      }
    } catch (error) {
      console.error('Erreur update auto-send:', error)
    }
  },
  
  setSessionId: (sessionId) => set({ sessionId }),
  
  setHistory: (history) => set({ history }),
  
  setStatistics: (stats) => set({ statistics: stats }),
  
  setAsrMode: (asrMode) => set({ asrMode }),
  
  setAiActive: (aiActive) => set({ aiActive }),
  
  setBibleVersion: (version) => get().selectBible(version),

  setSelectedEngine: (selectedEngine) => {
    set({ selectedEngine, _switchingEngine: true })
    // Sauvegarder la préférence de moteur au backend pour persistance
    fetch(`${BACKEND_BASE}/api/v1/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asr_default_engine: selectedEngine })
    }).catch((err) => console.error('Erreur sauvegarde moteur ASR:', err))

    const { isListening } = get()
    if (isListening) {
      get().disconnectWebSocket()
      setTimeout(() => {
        get().connectWebSocket()
        setTimeout(() => set({ _switchingEngine: false }), 1500)
      }, 300)
    } else {
      set({ _switchingEngine: false })
    }
  },
  
  setTranslationLang: (lang) => {
    set({ translationLang: lang, currentTranslation: '' })
    const { websocket, isListening } = get()
    if (websocket && isListening) {
      get().disconnectWebSocket()
      setTimeout(() => {
        get().connectWebSocket()
      }, 200)
    }
  },
  
  // WebSocket
  _manualDisconnect: false,
  _reconnectTimer: null,
  _connectionAttempts: 0,
  _everConnected: false,

  checkBackendHealth: async () => {
    const controller = new AbortController()
    // Au démarrage, le backend empaqueté charge ses index (Bible, flou 64 Mo,
    // sémantique 31k versets) et sa boucle peut rester bloquée plusieurs
    // secondes — mesuré à ~6 s sur un PC Windows. Une patience de 2,5 s le
    // déclarait « Hors ligne » alors qu'il démarrait normalement. On patiente
    // franchement tant qu'on n'a jamais été connecté, puis on redevient vif
    // pour détecter une vraie coupure pendant le direct.
    const everConnected = get()._everConnected || get().connected
    const timeout = setTimeout(() => controller.abort(), everConnected ? 2500 : 12000)
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/health`, { signal: controller.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      set({
        connected: true,
        backendUnreachable: false,
        connectionStatus: 'connected',
        _everConnected: true
      })
      return true
    } catch {
      set({
        connected: false,
        backendUnreachable: true,
        // Tant que le backend n'a jamais répondu, on est en démarrage, pas en
        // panne : le libellé « Hors ligne » alarmait à tort au premier lancement.
        connectionStatus: (get().isListening || !everConnected) ? (everConnected ? 'reconnecting' : 'starting') : 'disconnected'
      })
      return false
    } finally {
      clearTimeout(timeout)
    }
  },

  retryConnection: async () => {
    set({ _connectionAttempts: 0, _manualDisconnect: false })
    const healthy = await get().checkBackendHealth()
    if (healthy && get().isListening) return get().connectWebSocket()
    return healthy
  },

  connectWebSocket: () => {
    const existing = get().websocket
    if (existing?.readyState === WebSocket.OPEN) return Promise.resolve(existing)
    if (existing?.readyState === WebSocket.CONNECTING && connectPromise) return connectPromise

    const pendingTimer = get()._reconnectTimer
    if (pendingTimer) clearTimeout(pendingTimer)
    const { _everConnected, _connectionAttempts } = get()
    set({
      _manualDisconnect: false,
      _reconnectTimer: null,
      connectionStatus: _everConnected
        ? 'reconnecting'
        : (_connectionAttempts >= MAX_RECONNECT_ATTEMPTS ? 'disconnected' : 'starting')
    })

    const { selectedEngine, translationLang } = get()
    // En mode Tauri, le host est tauri.localhost → on pointe sur le backend
    const wsBase = BACKEND_WS_BASE || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    let wsUrl = `${wsBase}/ws/audio?engine=${selectedEngine}`
    if (translationLang) {
      wsUrl += `&translation_lang=${translationLang}`
    }
    connectPromise = new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'
      let opened = false

      ws.onopen = () => {
        opened = true
        set({
          websocket: ws,
          connected: true,
          audioConnected: true,
          connectionStatus: 'connected',
          backendUnreachable: false,
          _connectionAttempts: 0,
          _everConnected: true
        })
        resolve(ws)
      }

      ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.type === 'ai_status') {
        set({ aiActive: data.enabled })
      }
      
      if (data.type === 'status_update') {
        set({ asrMode: data.mode })
      }

      // Santé de la transcription : le backend ne signale que les BASCULES.
      // Quand le son se dégrade — musique de fond, voix couverte — les
      // propositions sémantiques sont suspendues et les citations annoncées
      // continuent de passer. Sans ce message, l'opérateur voit un logiciel
      // devenu muet et le croit en panne.
      if (data.type === 'transcription_health') {
        set({
          santeTranscription: {
            fiable: data.fiable,
            motsMoyens: data.mots_moyens,
            message: data.message,
          },
        })
      }

      if (data.type === 'transcript') {
        // Concatène le buffer validé et le fragment en cours d'écoute pour un affichage dynamique et continu
        const buffer = data.buffer || ''
        const currentText = data.text || ''
        
        let fullDisplay = ''
        if (data.is_final) {
          fullDisplay = buffer || currentText
        } else {
          fullDisplay = buffer ? `${buffer} ${currentText}`.trim() : currentText
        }
        
        set({ currentTranscript: fullDisplay })
      }
      
      if (data.type === 'translation') {
        set({ currentTranslation: data.text })
      }
      
      
      if (data.type === 'reference_detected') {
        get().addDetectedReference(data.reference)
        // Ajoute automatiquement à la file de projection (avec statut pending ou projected)
        get().addToProjectionQueue(data.reference)
        // Si le backend l'a projetée directement (autopilote), reflète l'état à l'antenne
        if (data.reference?.auto_projected) {
          set({
            onAir: {
              reference: data.reference.reference,
              text: data.reference.text || '',
              at: new Date().toISOString()
            }
          })
        }
        get().fetchHistory()
      }
      
      if (data.type === 'propresenter_status') {
        set({ propresenterConnected: data.sent })
      }
      
      if (data.type === 'ai_rejected_suggestion') {
        set({
          lastAiRejection: {
            reference: data.reference,
            confidence: data.confidence,
            threshold: data.threshold,
            reason: data.reason,
            time: new Date()
          }
        })
      }
      }

      ws.onclose = () => {
        const attempts = get()._connectionAttempts + 1
        const reconnect = shouldReconnect({
          manual: get()._manualDisconnect,
          listening: get().isListening,
          attempt: attempts
        })
        set({
          websocket: null,
          audioConnected: false,
          connectionStatus: reconnect ? 'reconnecting' : (get().connected ? 'connected' : 'disconnected'),
          currentTranslation: '',
          _connectionAttempts: attempts
        })
        if (!opened) reject(new Error('Connexion audio impossible'))
        if (reconnect) {
          const delay = reconnectDelay(attempts)
          const timer = setTimeout(() => {
            get().connectWebSocket().catch(() => {})
          }, delay)
          set({ _reconnectTimer: timer })
        } else if (attempts >= MAX_RECONNECT_ATTEMPTS && get().isListening) {
          set({ backendUnreachable: true, connectionStatus: 'disconnected' })
          get().addToast({ message: 'Connexion audio interrompue. Relancez après le contrôle serveur.', kind: 'error' })
        }
        get().checkBackendHealth()
      }

      ws.onerror = () => {
        if (!opened) set({ backendUnreachable: true })
      }

      set({ websocket: ws })
    })
    connectPromise.finally(() => { connectPromise = null }).catch(() => {})
    return connectPromise
  },
  
  disconnectWebSocket: () => {
    const { websocket, _reconnectTimer } = get()
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
    }
    set({ _manualDisconnect: true, _reconnectTimer: null, audioConnected: false })
    if (websocket) {
      websocket.close()
      set({
        websocket: null,
        connectionStatus: get().connected ? 'connected' : 'disconnected'
      })
    }
  },
  
  sendAudio: (audioChunk) => {
    const { websocket } = get()
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(audioChunk)
    }
  },
  
  // API calls
  fetchBibles: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/bibles`)
      const data = await response.json()
      set({ 
        activeBible: data.active || 'LSG', 
        availableBibles: data.versions || ['LSG'] 
      })
    } catch (error) {
      console.error('Erreur lors de la récupération des bibles:', error)
      set({ activeBible: 'LSG', availableBibles: ['LSG'] })
    }
  },

  fetchSettings: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/settings`)
      const data = await response.json()
      set({
        settings: data,
        autoSend: Boolean(data.auto_send),
        autopilotMode: Boolean(data.auto_send),
        activeBible: data.bible_version || get().activeBible,
        propresenterConnected: Boolean(data.propresenter_connected),
        aiActive: Boolean(data.ai_available),
        aiFilteringMode: data.ai_filtering_mode || 'strict',
        selectedEngine: data.asr_default_engine || get().selectedEngine,
        sundaySafeMode: data.sunday_safe_mode !== false,
        shadowMode: Boolean(data.shadow_mode),
        outputTheme: data.projection_theme || 'presentation',
        projectionStyle: data.projection_style || 'default',
        showBibleVersion: data.show_bible_version !== false,
        dualTranslations: data.dual_translations || 'LSG,KJF',
        vmixHost: data.vmix_host || '127.0.0.1',
        vmixPort: Number(data.vmix_port || 8088),
        vmixEnabled: String(data.vmix_enabled).toLowerCase() === 'true',
        vmixInputId: data.vmix_input_id || 'VerseProTitle'
      })
      return data
    } catch (error) {
      console.error('Erreur fetch settings:', error)
      return null
    }
  },

  updateSettings: async (patch) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch)
      })
      const data = await response.json()
      set({
        settings: data,
        autoSend: Boolean(data.auto_send),
        autopilotMode: Boolean(data.auto_send),
        activeBible: data.bible_version || get().activeBible,
        propresenterConnected: Boolean(data.propresenter_connected),
        aiActive: Boolean(data.ai_available),
        aiFilteringMode: data.ai_filtering_mode || 'strict',
        selectedEngine: data.asr_default_engine || get().selectedEngine,
        sundaySafeMode: data.sunday_safe_mode !== false,
        shadowMode: Boolean(data.shadow_mode),
        outputTheme: data.projection_theme || 'presentation',
        projectionStyle: data.projection_style || 'default',
        showBibleVersion: data.show_bible_version !== false,
        dualTranslations: data.dual_translations || 'LSG,KJF',
        vmixHost: data.vmix_host || get().vmixHost,
        vmixPort: Number(data.vmix_port || get().vmixPort),
        vmixEnabled: String(data.vmix_enabled).toLowerCase() === 'true',
        vmixInputId: data.vmix_input_id || get().vmixInputId
      })
      return data
    } catch (error) {
      console.error('Erreur update settings:', error)
      return null
    }
  },
  
  selectBible: async (version) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/bibles/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version })
      })
      const data = await response.json()
      if (data.status === 'success') {
        set({ activeBible: version })
        await fetch(`${BACKEND_BASE}/api/v1/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bible_version: version })
        })
      }
    } catch (error) {
      console.error('Erreur sélection bible:', error)
    }
  },
  
  fetchHistory: async () => {
    if (get().history.length === 0) set({ historyLoading: true })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/history/verses?limit=50`)
      const data = await response.json()
      set({ history: data.verses || [], backendUnreachable: false })
    } catch (error) {
      console.error('Erreur fetch history:', error)
      set({ backendUnreachable: true })
    } finally {
      set({ historyLoading: false })
    }
  },
  
  fetchStatistics: async (days = 30) => {
    if (!get().statistics) set({ statsLoading: true })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/statistics?days=${days}`)
      const data = await response.json()
      set({ statistics: data, backendUnreachable: false })
    } catch (error) {
      console.error('Erreur fetch statistics:', error)
      set({ backendUnreachable: true })
    } finally {
      set({ statsLoading: false })
    }
  },
  
  undoHistory: [],

  undoLastProjection: async () => {
    const history = get().undoHistory
    if (history.length === 0) {
      get().addToast({ message: 'Rien à annuler', kind: 'info' })
      return false
    }

    const previousState = history[history.length - 1]
    const nextHistory = history.slice(0, -1)
    set({ undoHistory: nextHistory })

    if (!previousState || !previousState.reference) {
      await get().clearProjectionScreen()
      get().addToast({ message: 'Annulé (⌘Z) : Écran effacé', kind: 'success' })
      return true
    }

    const sent = await get().sendReference(previousState.reference, previousState.version, true)
    if (sent) {
      get().addToast({ message: `Annulé (⌘Z) : Retour à ${previousState.reference} (${previousState.version || 'LSG'})`, kind: 'success' })
    }
    return sent
  },

  // ── Régie : préparer, voir, envoyer ────────────────────────────────────────
  //
  // Le geste fondamental d'une régie. Sans lui, valider une détection
  // l'envoyait DIRECTEMENT devant l'assemblée : l'opérateur découvrait le
  // rendu en même temps qu'elle, et ne pouvait plus rattraper un verset mal
  // coupé. La mécanique existait côté serveur ; il manquait les deux gestes.

  previewSlide: null,
  previewBusy: false,

  previewReference: async (reference, version = null) => {
    const ref = String(reference || '').trim()
    if (!ref) return false
    set({ previewBusy: true })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(version ? { reference: ref, version } : { reference: ref })
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || !data?.success) {
        get().addToast({ message: data?.detail || `Préparation impossible : ${ref}`, kind: 'error' })
        return false
      }
      set({
        previewSlide: {
          reference: data.reference,
          text: data.text || '',
          verses: data.verses || [],
          version: version || get().activeBible || 'LSG',
          at: new Date().toISOString()
        }
      })
      return true
    } catch (error) {
      console.error('Erreur de préparation:', error)
      get().addToast({ message: 'Serveur injoignable — préparation impossible', kind: 'error' })
      return false
    } finally {
      set({ previewBusy: false })
    }
  },

  takePreview: async () => {
    const monte = get().previewSlide
    if (!monte?.reference) return false
    set({ previewBusy: true })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/take`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || !data?.success) {
        get().addToast({ message: data?.detail || 'Envoi refusé', kind: 'error' })
        return false
      }
      // L'envoi ne passe pas par sendReference : sans cette ligne, la console
      // afficherait « écran noir » alors que l'assemblée lit le verset.
      const currentOnAir = get().onAir
      set((state) => ({
        onAir: {
          reference: data.reference || monte.reference,
          text: monte.text,
          at: new Date().toISOString(),
          version: monte.version
        },
        activeBible: monte.version || state.activeBible,
        undoHistory: currentOnAir
          ? [...state.undoHistory.slice(-19), { ...currentOnAir, version: state.activeBible }]
          : state.undoHistory
      }))
      get().addToast({ message: `À l'antenne : ${data.reference || monte.reference}`, kind: 'success' })
      return true
    } catch (error) {
      console.error('Erreur d\'envoi à l\'antenne:', error)
      get().addToast({ message: 'Serveur injoignable — envoi impossible', kind: 'error' })
      return false
    } finally {
      set({ previewBusy: false })
    }
  },

  // Au démarrage : si la console est rouverte en plein culte, elle retrouve ce
  // qui était monté au lieu d'afficher une préparation vide.
  fetchPreview: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/preview`)
      if (!response.ok) return
      const data = await response.json().catch(() => ({}))
      if (data?.reference) {
        set({
          previewSlide: {
            reference: data.reference,
            text: data.text || '',
            verses: data.verses || [],
            version: data.active_version || get().activeBible || 'LSG',
            at: new Date().toISOString()
          }
        })
      }
    } catch {
      // Console ouverte avant le backend : sans préparation, ce n'est pas une erreur.
    }
  },

  clearPreview: () => set({ previewSlide: null }),

  sendReference: async (reference, version = null, isUndo = false) => {
    try {
      const activeVersion = version || get().activeBible || 'LSG'
      // La version passe par SON champ, pas collée à la référence. L'ancien
      // « Jean 3:16:SEM » était simplement analysé comme « Jean 3:16 » puis le
      // suffixe jeté : le pasteur demandait la Semeur, l'assemblée lisait la
      // Segond, et l'interface affichait « ★ À l'antenne » sur la Semeur.

      // Sauvegarde dans l'historique d'annulation avant modification
      const currentOnAir = get().onAir
      if (!isUndo && currentOnAir) {
        set((state) => ({
          undoHistory: [...state.undoHistory.slice(-19), { ...currentOnAir, version: state.activeBible }]
        }))
      }

      const response = await fetch(`${BACKEND_BASE}/api/v1/references/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(version ? { reference, version } : { reference })
      })
      const data = await response.json().catch(() => ({}))
      if (response.ok && data?.success) {
        set({
          onAir: { reference: data.reference, text: data.text || '', at: new Date().toISOString(), version: activeVersion },
          activeBible: activeVersion,
          propresenterConnected: Boolean(data.propresenter_sent)
        })
        get().addToast({ message: `Projeté : ${data.reference} (${activeVersion})`, kind: 'success' })
      } else {
        get().addToast({ message: data?.detail || `Échec de projection : ${reference}`, kind: 'error' })
      }
      return Boolean(response.ok && data?.success)
    } catch (error) {
      console.error('Erreur send reference:', error)
      get().addToast({ message: 'Serveur injoignable — projection impossible', kind: 'error' })
      return false
    }
  },

  clearProjectionScreen: async () => {
    try {
      // Efface l'écran autonome + ProPresenter (meilleur effort)
      await fetch(`${BACKEND_BASE}/api/v1/project`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: '', reference: '' })
      })
      fetch(`${BACKEND_BASE}/api/v1/propresenter/clear`, { method: 'POST' }).catch(() => {})
      set({ onAir: null })
      get().addToast({ message: 'Écran effacé', kind: 'success' })
    } catch (error) {
      console.error('Erreur clear projection:', error)
    }
  },
  
  startSession: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/history/sessions/start`, {
        method: 'POST'
      })
      const data = await response.json()
      set({ sessionId: data.session_id })
      return data.session_id
    } catch (error) {
      console.error('Erreur start session:', error)
      return null
    }
  },
  
  endSession: async (sessionId) => {
    try {
      await fetch(`${BACKEND_BASE}/api/v1/history/sessions/${sessionId}/end`, {
        method: 'POST'
      })
      set({ sessionId: null })
      get().fetchSessions() // Rafraîchit la liste
    } catch (error) {
      console.error('Erreur end session:', error)
    }
  },
  
  fetchSessions: async (limit = 15) => {
    if (get().sessionsList.length === 0) set({ sessionsLoading: true })
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/history/sessions?limit=${limit}`)
      const data = await response.json()
      set({ sessionsList: data.sessions || [] })
    } catch (error) {
      console.error('Erreur fetch sessions:', error)
    } finally {
      set({ sessionsLoading: false })
    }
  },
  
  fetchSessionDetails: async (sessionId) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/history/sessions/${sessionId}`)
      if (response.ok) {
        const data = await response.json()
        set({ activeSessionDetails: data })
        return data
      }
    } catch (error) {
      console.error('Erreur fetch session details:', error)
    }
    return null
  },
  
  generateSessionSummary: async (sessionId) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/history/sessions/${sessionId}/summary`, {
        method: 'POST'
      })
      if (response.ok) {
        const data = await response.json()
        // Recharge les détails pour afficher le résumé mis à jour
        await get().fetchSessionDetails(sessionId)
        await get().fetchSessions() // Recharge aussi la liste
        return { summary: data.summary }
      }
      const errData = await response.json().catch(() => ({}))
      return { error: errData.detail || 'Échec de génération du résumé' }
    } catch (error) {
      console.error('Erreur generation résumé session:', error)
      return { error: 'Erreur réseau lors de la génération du résumé' }
    }
  },
  
  fetchVoskStatus: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/vosk/status`)
      const data = await response.json()
      set({ voskStatus: data })
      return data
    } catch (error) {
      console.error('Erreur fetch vosk status:', error)
      return null
    }
  },
  
  downloadVoskModel: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/vosk/download`, { method: 'POST' })
      const data = await response.json()
      get().fetchVoskStatus()
      const interval = setInterval(async () => {
        const status = await get().fetchVoskStatus()
        if (!status || !status.downloading) {
          clearInterval(interval)
        }
      }, 3000)
      return data
    } catch (error) {
      console.error('Erreur download vosk model:', error)
      return null
    }
  },

  fetchIntelligenceStatus: async () => {
    try {
      const [asrResponse, semanticResponse] = await Promise.all([
        fetch(`${BACKEND_BASE}/api/v1/asr/status`),
        fetch(`${BACKEND_BASE}/api/v1/semantic/status`)
      ])
      const asrStatus = asrResponse.ok ? await asrResponse.json() : null
      const semanticStatus = semanticResponse.ok ? await semanticResponse.json() : null
      set({ asrStatus, semanticStatus })
      return { asrStatus, semanticStatus }
    } catch (error) {
      console.error('Erreur statut intelligence locale:', error)
      return null
    }
  },


  prepareSemanticIndex: async () => {
    const response = await fetch(`${BACKEND_BASE}/api/v1/semantic/prepare`, { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    // Ne pas avaler un échec HTTP (503 service absent, etc.) : le remonter pour
    // que l'écran affiche la vraie cause au lieu d'un succès trompeur.
    if (!response.ok) throw new Error(data?.detail || `Erreur serveur ${response.status}`)
    get().fetchIntelligenceStatus()
    return data
  },

  // Prépare le moteur ASR local (Nemotron). Le backend ne prend plus de
  // nom de modèle : il n'y en a qu'un, et c'est lui qui décide où le poser.
  prepareLocalAsr: async () => {
    const response = await fetch(`${BACKEND_BASE}/api/v1/asr/prepare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || `Erreur serveur ${response.status}`)
    get().fetchIntelligenceStatus()
    return data
  },

  runPreflight: async ({ probeCloud = false, requireMicro = false } = {}) => {
    set({ preflightLoading: true })
    try {
      const response = await fetch(
        `${BACKEND_BASE}/api/v1/preflight?probe_cloud=${probeCloud ? 'true' : 'false'}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      if (requireMicro) {
        let micOk = false
        let detail = 'Aucune entrée audio détectée'
        try {
          const devices = await navigator.mediaDevices?.enumerateDevices?.() || []
          const inputs = devices.filter((device) => device.kind === 'audioinput')
          let permission = 'unknown'
          if (navigator.permissions?.query) {
            permission = (await navigator.permissions.query({ name: 'microphone' })).state
          }
          micOk = inputs.length > 0 && permission !== 'denied'
          detail = permission === 'denied'
            ? 'Permission microphone refusée'
            : `${inputs.length} entrée(s) audio détectée(s)`
        } catch {
          detail = 'Contrôle du microphone impossible'
        }
        data.checks.push({
          id: 'microphone',
          label: 'Entrée microphone',
          ok: micOk,
          critical: true,
          detail
        })
        data.ready = data.ready && micOk
      }
      set({ preflight: data, preflightCheckedAt: Date.now(), backendUnreachable: false })
      return data
    } catch {
      const data = {
        ready: false,
        checks: [{ id: 'server', label: 'Serveur VersePro', ok: false, critical: true, detail: 'Injoignable' }]
      }
      set({ preflight: data, preflightCheckedAt: Date.now(), backendUnreachable: true })
      return data
    } finally {
      set({ preflightLoading: false })
    }
  },

  activatePanicMode: async () => {
    get().stopRecording()
    try {
      await fetch(`${BACKEND_BASE}/api/v1/safety/panic`, { method: 'POST' })
    } catch { /* l'arrêt micro local reste effectif même sans serveur */ }
    set({
      autoSend: false,
      autopilotMode: false,
      sundaySafeMode: true,
      shadowMode: false,
      onAir: null
    })
    get().addToast({ message: 'Mode sûr activé. Automatisations coupées et écran effacé.', kind: 'success' })
  },
  
  setOutputTheme: async (theme) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/theme`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme })
      })
      if (response.ok) {
        set({ outputTheme: theme })
      }
    } catch (e) {
      console.error('Erreur theme:', e)
    }
  },

  updateVMixConfig: async (config) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/vmix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      if (response.ok) {
        set({
          vmixHost: config.host || '127.0.0.1',
          vmixPort: config.port || 8088,
          vmixEnabled: config.enabled || false,
          vmixInputId: config.input_id || 'VerseProTitle'
        })
        get().addToast({ message: 'Configuration vMix mise à jour', kind: 'success' })
      }
    } catch (e) {
      get().addToast({ message: 'Échec de configuration vMix', kind: 'error' })
    }
  },

  setVolume: (volume) => set({ volume }),
  setSelectedAudioDeviceId: (id) => {
    try { localStorage.setItem('versepro_audio_device_id', id) } catch {}
    set({ selectedAudioDeviceId: id })
  },
  setAudioFilterMode: (mode) => {
    const safeMode = ['off', 'speech', 'church'].includes(mode) ? mode : 'off'
    try { localStorage.setItem('versepro_audio_filter_mode', safeMode) } catch {}
    set({ audioFilterMode: safeMode })
  },
  setMicPermissionState: (state) => set({ micPermissionState: state }),
  setMicError: (error) => set({ micError: error }),
  
  refreshAudioDevices: async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const inputs = devices.filter((device) => device.kind === 'audioinput')
      set({ audioDevices: inputs })
      
      const current = get().selectedAudioDeviceId
      const saved = (() => {
        try { return localStorage.getItem('versepro_audio_device_id') || '' } catch { return '' }
      })()
      const next = current || saved || inputs[0]?.deviceId || ''
      if (next && inputs.some((device) => device.deviceId === next)) {
        set({ selectedAudioDeviceId: next })
      } else if (inputs[0]?.deviceId) {
        set({ selectedAudioDeviceId: inputs[0].deviceId })
      }
    } catch (error) {
      console.warn('Impossible de lire les entrées micro:', error)
    }
  },

  startRecording: async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Ce navigateur ne donne pas accès au micro.')
    }
    set({ micError: null })
    const { preflight, preflightCheckedAt = 0 } = get()
    const freshPreflight = Date.now() - preflightCheckedAt < 15000
      ? preflight
      : await get().runPreflight()
    if (!freshPreflight?.ready) {
      // Fail-open : un contrôle incomplet avertit mais ne bloque jamais le
      // direct. Le seul arrêt réel reste un serveur audio injoignable, traité
      // juste en dessous par l'échec de connexion WebSocket.
      get().addToast({
        message: 'Contrôle avant direct incomplet : écoute démarrée, vérifiez la régie.',
        kind: 'error',
        duration: 6000
      })
    }
    try {
      await get().connectWebSocket()
    } catch {
      set({ micError: 'Le moteur VersePro ne répond pas.', backendUnreachable: true })
      get().addToast({ message: 'Impossible de démarrer: serveur audio indisponible.', kind: 'error' })
      throw new Error('Serveur audio indisponible')
    }
    const { selectedAudioDeviceId } = get()
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

    try {
      const streamObj = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints })
      mediaStream = streamObj
      set({ micPermissionState: 'granted' })
      get().refreshAudioDevices()

      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      const audioCtx = new AudioContextClass()
      if (audioCtx.state === 'suspended') await audioCtx.resume()
      audioContext = audioCtx

      const sourceNode = audioCtx.createMediaStreamSource(streamObj)

      const { audioFilterMode } = get()
      let highpassNode = null
      let lowpassNode = null
      if (audioFilterMode !== 'off') {
        highpassNode = audioCtx.createBiquadFilter()
        highpassNode.type = 'highpass'
        highpassNode.frequency.value = audioFilterMode === 'church' ? 120 : 80
        lowpassNode = audioCtx.createBiquadFilter()
        lowpassNode.type = 'lowpass'
        lowpassNode.frequency.value = audioFilterMode === 'church' ? 7000 : 8000
      }

      const inputSampleRate = audioCtx.sampleRate

      const handleAudioFrame = (inputData) => {
        if (!mediaStream) return
        let sum = 0
        for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i]
        const rms = Math.sqrt(sum / inputData.length)
        const points = 64
        const waveform = Array.from({ length: points }, (_, point) => {
          const start = Math.floor((point * inputData.length) / points)
          const end = Math.max(start + 1, Math.floor(((point + 1) * inputData.length) / points))
          let peak = 0
          for (let index = start; index < end && index < inputData.length; index++) {
            if (Math.abs(inputData[index]) > Math.abs(peak)) peak = inputData[index]
          }
          return peak
        })
        set({ volume: Math.min(100, Math.round(rms * 600)), waveform })

        const downsampled = downsampleBuffer(inputData, inputSampleRate, 16000)
        const pcmBuffer = new Int16Array(downsampled.length)
        for (let i = 0; i < downsampled.length; i++) {
          const s = Math.max(-1, Math.min(1, downsampled[i]))
          pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        get().sendAudio(pcmBuffer.buffer)
      }

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
                // 2048 échantillons ≈ 43 ms à 48 kHz : la moitié de latence de
                // groupage d'avant, sans surcoût mesurable pour les moteurs ASR.
                if (this._length >= 2048) {
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
        await audioCtx.audioWorklet.addModule(moduleUrl)
        URL.revokeObjectURL(moduleUrl)
        captureNode = new AudioWorkletNode(audioCtx, 'vp-pcm-forwarder')
        captureNode.port.onmessage = (event) => handleAudioFrame(event.data)
        console.info('Capture audio : AudioWorklet global')
      } catch (workletErr) {
        console.warn('AudioWorklet indisponible, repli sur ScriptProcessor :', workletErr)
        captureNode = audioCtx.createScriptProcessor(2048, 1, 1)
        captureNode.onaudioprocess = (event) => handleAudioFrame(event.inputBuffer.getChannelData(0))
      }
      processorNode = captureNode

      if (highpassNode && lowpassNode) {
        sourceNode.connect(highpassNode)
        highpassNode.connect(lowpassNode)
        lowpassNode.connect(captureNode)
      } else {
        sourceNode.connect(captureNode)
      }
      captureNode.connect(audioCtx.destination)
      set({ isListening: true, listeningStartedAt: Date.now(), listeningStoppedAt: null })
    } catch (err) {
      console.error("Erreur d'accès micro:", err)
      set({ micError: "Impossible d'accéder au microphone.", isListening: false })
      get().disconnectWebSocket()
      throw err
    }
  },

  stopRecording: () => {
    set({ volume: 0, waveform: Array(64).fill(0), isListening: false, listeningStoppedAt: Date.now() })
    if (processorNode) {
      processorNode.disconnect()
      processorNode = null
    }
    if (audioContext) {
      audioContext.close()
      audioContext = null
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop())
      mediaStream = null
    }
    get().disconnectWebSocket()
  },

  toggleListening: async () => {
    const { isListening, startRecording, stopRecording } = get()
    if (isListening) {
      stopRecording()
    } else {
      try {
        await startRecording()
      } catch (e) {
        // Erreur déjà capturée dans startRecording
      }
    }
  }
}))
