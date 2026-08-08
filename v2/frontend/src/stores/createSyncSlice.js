import { BACKEND_BASE, BACKEND_WS_BASE } from '../env.js'
import { MAX_RECONNECT_ATTEMPTS, reconnectDelay, shouldReconnect } from '../runtime/reconnect.js'

let connectPromise = null

export const createSyncSlice = (set, get) => ({
  connected: false,
  audioConnected: false,
  connectionStatus: 'starting', // starting | connected | reconnecting | disconnected
  websocket: null,

  currentTranscript: '',
  detectedReferences: [],
  asrMode: 'deepgram',
  santeTranscription: { fiable: true, motsMoyens: 0, message: '' },
  selectedEngine: 'auto',
  aiActive: false,

  translationLang: '',
  currentTranslation: '',

  _manualDisconnect: false,
  _reconnectTimer: null,
  _connectionAttempts: 0,
  _everConnected: false,

  setConnected: (connected) => set({
    connected,
    connectionStatus: connected ? 'connected' : 'disconnected'
  }),

  setWebsocket: (ws) => set({ websocket: ws }),

  setCurrentTranscript: (transcript) => set({ currentTranscript: transcript }),

  addDetectedReference: (reference) => set((state) => ({
    detectedReferences: [reference, ...state.detectedReferences]
  })),

  setAsrMode: (asrMode) => set({ asrMode }),

  setAiActive: (aiActive) => set({ aiActive }),

  setSelectedEngine: (selectedEngine) => {
    const prevEngine = get().selectedEngine
    set({ selectedEngine, _switchingEngine: true })

    fetch(`${BACKEND_BASE}/api/v1/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asr_default_engine: selectedEngine })
    }).catch(() => {})

    const timer = get()._reconnectTimer
    if (timer) {
      clearTimeout(timer)
      set({ _reconnectTimer: null })
    }

    const { isListening, websocket } = get()
    if (websocket) {
      set({ websocket: null, _manualDisconnect: true })
      try {
        websocket.onclose = null
        websocket.close()
      } catch (e) {}
    }

    set({ _connectionAttempts: 0, _manualDisconnect: false, _switchingEngine: false })

    if (isListening) {
      setTimeout(() => {
        get().connectWebSocket().catch(() => {})
      }, 80)
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

  checkBackendHealth: async () => {
    const controller = new AbortController()
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
        if (data.status === 'fallback') {
          const msg = data.reason || `Le moteur demandé n'est pas prêt. Repli sur ${data.mode}.`
          get().addToast({ message: msg, kind: 'warn' })
        }
      }

      if (data.type === 'transcription_health') {
        // set({
        //   santeTranscription: {
        //     fiable: data.fiable,
        //     motsMoyens: data.mots_moyens,
        //     message: data.message,
        //   },
        // })
      }

      if (data.type === 'transcript') {
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
        get().addToProjectionQueue(data.reference)
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
        if (get().websocket !== ws) {
          return
        }
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
  }
})
