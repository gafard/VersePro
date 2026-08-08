import { BACKEND_BASE } from '../env.js'

export const createHistorySlice = (set, get) => ({
  sessionId: null,
  sessionsList: [], // Liste des sessions enregistrées
  activeSessionDetails: null, // Détails de la session en cours de visualisation (transcript, summary)
  history: [],
  statistics: null,

  setSessionId: (sessionId) => set({ sessionId }),

  setHistory: (history) => set({ history }),

  setStatistics: (stats) => set({ statistics: stats }),

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
  }
})
