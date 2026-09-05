import { isTauri } from '../env.js'

const initialInfo = {
  current: null,
  latest: null,
  update_available: false,
  notes: null,
  date: null,
  checked: false
}

const invokeDesktop = (command, payload) => {
  const invoke = window.__TAURI__?.core?.invoke
  if (typeof invoke !== 'function') throw new Error('Updater disponible uniquement dans VersePro installé.')
  return invoke(command, payload)
}

export const createUpdateSlice = (set, get) => ({
  desktopUpdateInfo: initialInfo,
  desktopUpdateStatus: isTauri ? 'idle' : 'unsupported',
  desktopUpdateError: null,
  desktopUpdateProgress: { downloaded: 0, total: null, percent: 0 },
  desktopUpdateDialogOpen: false,

  setDesktopUpdateProgress: ({ phase, downloaded = 0, total = null }) => {
    const percent = total && total > 0
      ? Math.min(100, Math.round((downloaded / total) * 100))
      : 0
    set({
      desktopUpdateStatus: phase === 'install' ? 'installing' : 'downloading',
      desktopUpdateProgress: { downloaded, total, percent }
    })
  },

  dismissDesktopUpdate: () => set({ desktopUpdateDialogOpen: false }),
  openDesktopUpdate: () => set((state) => ({
    desktopUpdateDialogOpen: Boolean(state.desktopUpdateInfo.update_available)
  })),

  checkDesktopUpdate: async ({ silent = false } = {}) => {
    if (!isTauri) return null
    set({ desktopUpdateStatus: 'checking', desktopUpdateError: null })
    try {
      const info = await invokeDesktop('verifier_mise_a_jour')
      set({
        desktopUpdateInfo: info,
        desktopUpdateStatus: info.update_available ? 'available' : 'current',
        desktopUpdateDialogOpen: Boolean(info.update_available)
      })
      if (!silent && !info.update_available) {
        get().addToast({ message: `VersePro ${info.current} est à jour`, kind: 'success' })
      }
      return info
    } catch (error) {
      const message = String(error?.message || error || 'Contrôle de mise à jour indisponible')
      set({ desktopUpdateStatus: 'error', desktopUpdateError: message })
      if (!silent) get().addToast({ message, kind: 'error', duration: 7000 })
      return null
    }
  },

  installDesktopUpdate: async () => {
    const { isListening, onAir } = get()
    if (isListening || onAir) {
      const message = 'Arrêtez le micro et videz la sortie à l’antenne avant la mise à jour.'
      set({ desktopUpdateError: message })
      get().addToast({ message, kind: 'error', duration: 7000 })
      return false
    }

    set({
      desktopUpdateStatus: 'downloading',
      desktopUpdateError: null,
      desktopUpdateProgress: { downloaded: 0, total: null, percent: 0 }
    })
    try {
      await invokeDesktop('installer_mise_a_jour')
      return true
    } catch (error) {
      const message = String(error?.message || error || 'Installation de la mise à jour impossible')
      set({ desktopUpdateStatus: 'error', desktopUpdateError: message })
      get().addToast({ message, kind: 'error', duration: 8000 })
      return false
    }
  }
})
