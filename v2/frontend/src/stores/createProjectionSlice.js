import { BACKEND_BASE } from '../env.js'

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

export const createProjectionSlice = (set, get) => ({
  propresenterConnected: false,
  autoSend: false,
  autopilotMode: true, // true: envoie direct, false: met en attente dans la file
  projectionQueue: [], // Liste des versets détectés en attente de projection
  preparedVerses: readPreparedVerses(), // Déroulé préparé, conservé entre deux lancements
  onAir: null,

  activeBible: 'LSG',
  availableBibles: ['LSG'],

  previewSlide: null,
  previewBusy: false,
  undoHistory: [],

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

  fetchProjectionState: async () => {
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/projection/current`)
      if (!response.ok) return
      const data = await response.json()
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

  setPropresenterConnected: (connected) => set({ propresenterConnected: connected }),

  setAutopilotMode: async (mode) => {
    await get().setAutoSend(mode)
  },

  addToProjectionQueue: (verse) => set((state) => {
    if (!verse || !verse.reference) return {}

    // Évite les doublons : si le verset est déjà en attente ("pending"), on met à jour son heure/confiance sans recréer de carte
    const existingIndex = state.projectionQueue.findIndex(
      (item) => item.status === 'pending' && item.reference.toLowerCase().trim() === verse.reference.toLowerCase().trim()
    )

    if (existingIndex !== -1) {
      const updatedQueue = [...state.projectionQueue]
      updatedQueue[existingIndex] = {
        ...updatedQueue[existingIndex],
        detectedAt: verse.detected_at || new Date().toISOString(),
        confidence: verse.confidence || updatedQueue[existingIndex].confidence,
        detectedFrom: verse.detected_from || verse.transcript || updatedQueue[existingIndex].detectedFrom
      }
      return { projectionQueue: updatedQueue }
    }

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

  // Efface uniquement les détections de la file « À valider ». Le déroulé
  // préparé est un état séparé et ne doit jamais être touché par cette action.
  clearDetectedVerses: () => {
    const previous = get().projectionQueue
    if (previous.length === 0) return
    set({ projectionQueue: [] })
    get().addToast({
      message: `Détections vidées (${previous.length} élément${previous.length > 1 ? 's' : ''})`,
      kind: 'success',
      action: { label: 'Annuler', onClick: () => set({ projectionQueue: previous }) }
    })
  },

  // Alias conservé pour les intégrations existantes.
  clearProjectionQueue: () => get().clearDetectedVerses(),

  prepareReference: async (query) => {
    let requested = String(query || '').trim()
    if (!requested) return null

    // Résolution contextuelle : si l'utilisateur tape un simple numéro (ex: "21") alors qu'un verset (ex: Jean 3:16) est à l'antenne
    const activeOnAirRef = get().onAir?.reference || get().projectionQueue.find((item) => item.status === 'projected')?.reference
    const numberMatch = /^(?:v\.?\s*)?(\d+)(?:\s*-\s*(\d+))?$/i.exec(requested)
    if (numberMatch && activeOnAirRef) {
      const verseMatch = /^(.+?)\s+(\d+):(\d+)/.exec(activeOnAirRef)
      if (verseMatch) {
        const bookChap = `${verseMatch[1]} ${verseMatch[2]}`
        const startV = numberMatch[1]
        const endV = numberMatch[2]
        requested = endV ? `${bookChap}:${startV}-${endV}` : `${bookChap}:${startV}`
      }
    }

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
          propresenterConnected: Boolean(data.propresenter_connected),
          sundaySafeMode: data.sunday_safe_mode !== false,
        })
      }
    } catch (error) {
      console.error('Erreur update auto-send:', error)
    }
  },

  setBibleVersion: (version) => get().selectBible(version),

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
    }
  },

  clearPreview: () => set({ previewSlide: null }),

  sendReference: async (reference, version = null, isUndo = false) => {
    try {
      let targetRef = String(reference || '').trim()
      if (!targetRef) return false

      // Résolution contextuelle : si l'utilisateur tape un simple numéro (ex: "21") alors qu'un verset (ex: Jean 3:16) est à l'antenne
      const activeOnAirRef = get().onAir?.reference || get().projectionQueue.find((item) => item.status === 'projected')?.reference
      const numberMatch = /^(?:v\.?\s*)?(\d+)(?:\s*-\s*(\d+))?$/i.exec(targetRef)
      if (numberMatch && activeOnAirRef) {
        const verseMatch = /^(.+?)\s+(\d+):(\d+)/.exec(activeOnAirRef)
        if (verseMatch) {
          const bookChap = `${verseMatch[1]} ${verseMatch[2]}`
          const startV = numberMatch[1]
          const endV = numberMatch[2]
          targetRef = endV ? `${bookChap}:${startV}-${endV}` : `${bookChap}:${startV}`
        }
      }

      const activeVersion = version || get().activeBible || 'LSG'
      const currentOnAir = get().onAir
      if (!isUndo && currentOnAir) {
        set((state) => ({
          undoHistory: [...state.undoHistory.slice(-19), { ...currentOnAir, version: state.activeBible }]
        }))
      }

      const response = await fetch(`${BACKEND_BASE}/api/v1/references/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reference: targetRef, version: activeVersion })
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
  }
})
