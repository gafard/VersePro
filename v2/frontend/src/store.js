import { create } from 'zustand'
import { createAudioSlice } from './stores/createAudioSlice.js'
import { createHistorySlice } from './stores/createHistorySlice.js'
import { createProjectionSlice } from './stores/createProjectionSlice.js'
import { createSyncSlice } from './stores/createSyncSlice.js'
import { createUiSlice } from './stores/createUiSlice.js'

export const useStore = create((set, get) => ({
  ...createAudioSlice(set, get),
  ...createHistorySlice(set, get),
  ...createProjectionSlice(set, get),
  ...createSyncSlice(set, get),
  ...createUiSlice(set, get)
}))
