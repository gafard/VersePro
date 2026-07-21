import { create } from 'zustand'
import { BACKEND_BASE, BACKEND_WS_BASE } from './env.js'

// Variables non-réactives de module privées pour la capture audio globale
let audioContext = null
let mediaStream = null
let processorNode = null

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
  connectionStatus: 'starting', // starting | connected | reconnecting | disconnected
  websocket: null,
  
  // État de détection et ASR
  isListening: false,
  volume: 0,
  audioDevices: [],
  selectedAudioDeviceId: (() => {
    try { return localStorage.getItem('versepro_audio_device_id') || '' } catch { return '' }
  })(),
  micPermissionState: 'unknown',
  micError: null,
  currentTranscript: '',
  detectedReferences: [],
  asrMode: 'deepgram', // deepgram ou vosk
  selectedEngine: 'auto', // auto, deepgram ou vosk
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
      source: verse.source || (['ai_semantic', 'semantic_local'].includes(verse.detection_method) ? 'semantic' : 'local'),
      detectionMethod: verse.detection_method,
      projectionPolicy: verse.projection_policy || (verse.requires_review ? 'manual_review' : 'manual_queue'),
      requiresReview: Boolean(verse.requires_review),
      status: wasAutoProjected ? 'projected' : 'pending' // 'pending' | 'projected' | 'rejected'
    }
    return {
      projectionQueue: [newEntry, ...state.projectionQueue]
    }
  }),
  
  projectVerseFromQueue: async (queueId, reference, text) => {
    // 1. Envoi au ProPresenter
    const sent = await get().sendReference(reference)
    
    // 2. Met à jour le statut dans la file
    set((state) => ({
      projectionQueue: state.projectionQueue.map((item) => 
        item.queueId === queueId ? { ...item, status: 'projected' } : item
      )
    }))
    
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
  
  setSelectedEngine: (selectedEngine) => {
    set({ selectedEngine, _switchingEngine: true })
    const { websocket } = get()
    if (websocket) {
      get().disconnectWebSocket()
      // Un court délai permet de s'assurer de la fermeture propre avant reconnexion
      setTimeout(() => {
        get().connectWebSocket()
        // Laisse le temps au onopen de se déclencher avant de lever le flag
        setTimeout(() => set({ _switchingEngine: false }), 1500)
      }, 200)
    } else {
      set({ _switchingEngine: false })
    }
  },
  
  setTranslationLang: (lang) => {
    set({ translationLang: lang, currentTranslation: '' })
    const { websocket } = get()
    if (websocket) {
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

  connectWebSocket: () => {
    // Annule une éventuelle reconnexion programmée (évite les connexions en double)
    const pendingTimer = get()._reconnectTimer
    if (pendingTimer) {
      clearTimeout(pendingTimer)
    }
    const { _everConnected, _connectionAttempts } = get()
    set({
      _manualDisconnect: false,
      _reconnectTimer: null,
      connectionStatus: _everConnected
        ? 'reconnecting'
        : (_connectionAttempts >= 8 ? 'disconnected' : 'starting')
    })

    const { selectedEngine, translationLang } = get()
    // En mode Tauri, le host est tauri.localhost → on pointe sur le backend
    const wsBase = BACKEND_WS_BASE || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    let wsUrl = `${wsBase}/ws/audio?engine=${selectedEngine}`
    if (translationLang) {
      wsUrl += `&translation_lang=${translationLang}`
    }
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    
    ws.onopen = () => {
      console.log('WebSocket connecté')
      set({
        connected: true,
        connectionStatus: 'connected',
        backendUnreachable: false,
        _connectionAttempts: 0,
        _everConnected: true
      })
      // Récupère les traductions, réglages et l'état de projection courant
      get().fetchBibles()
      get().fetchSettings()
      get().fetchProjectionState()
      get().hydrateQueueFromSession()
    }
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.type === 'ai_status') {
        set({ aiActive: data.enabled })
      }
      
      if (data.type === 'status_update') {
        set({ asrMode: data.mode })
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
      console.log('WebSocket déconnecté')
      const attempts = get()._connectionAttempts + 1
      const everConnected = get()._everConnected
      set({
        connected: false,
        connectionStatus: everConnected
          ? 'reconnecting'
          : (attempts >= 8 ? 'disconnected' : 'starting'),
        aiActive: false,
        currentTranslation: '',
        _connectionAttempts: attempts
      })
      // Reconnexion automatique après une coupure involontaire (réseau, redémarrage backend)
      if (!get()._manualDisconnect) {
        console.log('Reconnexion automatique dans 2s...')
        const timer = setTimeout(() => get().connectWebSocket(), 2000)
        set({ _reconnectTimer: timer })
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket erreur:', error)
    }
    
    set({ websocket: ws })
  },
  
  disconnectWebSocket: () => {
    const { websocket, _reconnectTimer } = get()
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
    }
    set({ _manualDisconnect: true, _reconnectTimer: null })
    if (websocket) {
      websocket.close()
      set({
        websocket: null,
        connected: false,
        connectionStatus: get()._everConnected ? 'reconnecting' : 'starting'
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
  
  sendReference: async (reference) => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/references/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reference })
      })
      const data = await response.json()
      if (data?.success) {
        set({
          onAir: { reference: data.reference, text: data.text || '', at: new Date().toISOString() },
          propresenterConnected: Boolean(data.propresenter_sent)
        })
        get().addToast({ message: `Projeté : ${data.reference}`, kind: 'success' })
      } else {
        get().addToast({ message: data?.detail || `Échec de projection : ${reference}`, kind: 'error' })
      }
      return data
    } catch (error) {
      console.error('Erreur send reference:', error)
      get().addToast({ message: 'Serveur injoignable — projection impossible', kind: 'error' })
      return null
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
    const data = await response.json()
    get().fetchIntelligenceStatus()
    return data
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

      const highpassNode = audioCtx.createBiquadFilter()
      highpassNode.type = 'highpass'
      highpassNode.frequency.value = 250
      const lowpassNode = audioCtx.createBiquadFilter()
      lowpassNode.type = 'lowpass'
      lowpassNode.frequency.value = 3000

      const inputSampleRate = audioCtx.sampleRate

      const handleAudioFrame = (inputData) => {
        if (!mediaStream) return
        let sum = 0
        for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i]
        const rms = Math.sqrt(sum / inputData.length)
        set({ volume: Math.min(100, Math.round(rms * 600)) })

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
        await audioCtx.audioWorklet.addModule(moduleUrl)
        URL.revokeObjectURL(moduleUrl)
        captureNode = new AudioWorkletNode(audioCtx, 'vp-pcm-forwarder')
        captureNode.port.onmessage = (event) => handleAudioFrame(event.data)
        console.info('Capture audio : AudioWorklet global')
      } catch (workletErr) {
        console.warn('AudioWorklet indisponible, repli sur ScriptProcessor :', workletErr)
        captureNode = audioCtx.createScriptProcessor(4096, 1, 1)
        captureNode.onaudioprocess = (event) => handleAudioFrame(event.inputBuffer.getChannelData(0))
      }
      processorNode = captureNode

      sourceNode.connect(highpassNode)
      highpassNode.connect(lowpassNode)
      lowpassNode.connect(captureNode)
      captureNode.connect(audioCtx.destination)
      set({ isListening: true })
    } catch (err) {
      console.error("Erreur d'accès micro:", err)
      set({ micError: "Impossible d'accéder au microphone.", isListening: false })
      throw err
    }
  },

  stopRecording: () => {
    set({ volume: 0, isListening: false })
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
