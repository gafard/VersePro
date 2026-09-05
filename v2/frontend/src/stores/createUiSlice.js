import { BACKEND_BASE } from '../env.js'

export const createUiSlice = (set, get) => ({
  toasts: [],
  addToast: ({ message, kind = 'success', action = null, duration = 3500 }) => {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    set((state) => ({ toasts: [...state.toasts.slice(-2), { id, message, kind, action }] }))
    setTimeout(() => get().dismissToast(id), action ? 6000 : duration)
    return id
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  historyLoading: false,
  sessionsLoading: false,
  statsLoading: false,
  backendUnreachable: false,

  settings: null,
  aiFilteringMode: 'strict', // 'strict' ou 'open'
  lastAiRejection: null,

  outputTheme: 'presentation',
  projectionStyle: 'default',
  showBibleVersion: true,
  dualTranslations: 'LSG,KJF',
  vmixEnabled: false,
  vmixHost: '127.0.0.1',
  vmixPort: 8088,
  vmixInputId: 'VerseProTitle',

  voskStatus: { installed: false, downloading: false, model_name: '', model_type: '' },
  asrStatus: null,
  semanticStatus: null,
  preflight: null,
  preflightLoading: false,
  sundaySafeMode: true,
  shadowMode: false,

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
      if (!response.ok) throw new Error('Les réglages n’ont pas pu être enregistrés.')
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
    if (!response.ok) throw new Error(data?.detail || `Erreur serveur ${response.status}`)
    get().fetchIntelligenceStatus()
    const interval = setInterval(async () => {
      const status = await get().fetchIntelligenceStatus()
      if (!status?.semanticStatus || !status.semanticStatus.downloading) {
        clearInterval(interval)
      }
    }, 1000)
    return data
  },

  prepareLocalAsr: async () => {
    const response = await fetch(`${BACKEND_BASE}/api/v1/asr/prepare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || `Erreur serveur ${response.status}`)
    get().fetchIntelligenceStatus()
    const interval = setInterval(async () => {
      const status = await get().fetchIntelligenceStatus()
      if (!status?.asrStatus?.nemotron?.downloading) {
        clearInterval(interval)
      }
    }, 1000)
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
  }
})
