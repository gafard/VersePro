let audioContext = null
let mediaStream = null
let processorNode = null
let silenceTimer = null

// SURVEILLANCE DU SILENCE — la panne qui ne se voyait pas.
//
// Mesuré sur le journal du 9 août : le micro était « actif », les blocs audio
// arrivaient au backend toutes les 43 ms, Deepgram PUIS Nemotron ont tourné
// deux minutes chacun — zéro mot. Le flux était vide. À l'écran, VersePro
// affichait « en attente de parole », c'est-à-dire exactement ce qu'il affiche
// quand tout va bien et que personne ne parle. Rien ne distinguait un micro
// mort d'un silence normal.
//
// Le plancher est délibérément TRÈS bas. Une salle vide, un micro coupé au
// pupitre, une respiration : tout cela dépasse 0,0008 de RMS. Seul un flux
// réellement sans signal — entrée débranchée, micro Continuité dont l'iPhone
// dort, périphérique virtuel sans source — reste en dessous. On ne crie donc
// jamais au loup pendant une pause de la prédication.
const PLANCHER_SIGNAL = 0.0008
const DELAI_SILENCE_MS = 8000
let dernierSon = 0

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

export const createAudioSlice = (set, get) => ({
  isListening: false,
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
  micSilent: false,

  setIsListening: (isListening) => set({ isListening }),

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

  // NE CHOISIT JAMAIS LE MICRO À LA PLACE DE L'OPÉRATEUR.
  //
  // La version précédente retombait sur `inputs[0]` — le PREMIER de la liste
  // CoreAudio, pas le micro par défaut du système. Sur ce Mac, le premier est
  // « Micro de "iPhone" » (Continuité) ; le micro intégré arrive second. Au
  // premier démarrage le navigateur ouvrait bien le défaut système et tout
  // marchait, puis ce rafraîchissement inscrivait l'iPhone dans l'état — et le
  // démarrage SUIVANT le rouvrait avec `deviceId: { exact }`. Téléphone
  // verrouillé ou éloigné : un flux qui existe, qui débite des blocs, et qui
  // ne contient rien.
  //
  // Une chaîne vide signifie désormais « entrée par défaut du système ».
  // C'est le bon défaut : le régisseur a déjà choisi son entrée dans macOS ou
  // Windows, et personne n'a jamais demandé à VersePro de la contredire.
  refreshAudioDevices: async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const inputs = devices.filter((device) => device.kind === 'audioinput')
      set({ audioDevices: inputs })

      // Un choix explicite qui a disparu (micro débranché entre deux cultes)
      // repart au défaut système plutôt que de faire échouer `exact`.
      const current = get().selectedAudioDeviceId
      if (current && inputs.length && !inputs.some((device) => device.deviceId === current)) {
        try { localStorage.removeItem('versepro_audio_device_id') } catch {}
        set({ selectedAudioDeviceId: '' })
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
      get().addToast({
        message: 'Contrôle avant direct incomplet : écoute démarrée, vérifiez la régie.',
        kind: 'error',
        duration: 6000
      })
    }
    try {
      await get().connectWebSocket()
    } catch (error) {
      const detail = error?.message || 'Serveur audio indisponible'
      set({ micError: `Le canal audio ne répond pas : ${detail}.`, backendUnreachable: true })
      get().addToast({ message: `Impossible de démarrer le micro : ${detail}.`, kind: 'error', duration: 8000 })
      throw error
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
      let streamObj
      try {
        streamObj = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints })
      } catch (constraintErr) {
        // Le micro choisi n'existe plus. Un dimanche matin, refuser d'ouvrir
        // le micro pour ça serait absurde : on prend le défaut système et on
        // le DIT, au lieu de laisser l'opérateur devant un bouton mort.
        if (!selectedAudioDeviceId) throw constraintErr
        console.warn('Micro sélectionné indisponible, repli sur le défaut système :', constraintErr)
        try { localStorage.removeItem('versepro_audio_device_id') } catch {}
        set({ selectedAudioDeviceId: '' })
        streamObj = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
        })
        get().addToast({
          message: 'Micro sélectionné introuvable : entrée par défaut du système utilisée.',
          kind: 'warn',
          duration: 7000
        })
      }
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
        if (rms > PLANCHER_SIGNAL) {
          dernierSon = Date.now()
          if (get().micSilent) set({ micSilent: false })
        }
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
      dernierSon = Date.now()
      if (silenceTimer) clearInterval(silenceTimer)
      silenceTimer = setInterval(() => {
        if (!get().isListening) return
        const muet = Date.now() - dernierSon > DELAI_SILENCE_MS
        if (muet !== get().micSilent) set({ micSilent: muet })
      }, 1000)
      set({ isListening: true, micSilent: false, listeningStartedAt: Date.now(), listeningStoppedAt: null })
    } catch (err) {
      console.error("Erreur d'accès micro:", err)
      set({ micError: "Impossible d'accéder au microphone.", isListening: false })
      get().disconnectWebSocket()
      throw err
    }
  },

  stopRecording: () => {
    if (silenceTimer) {
      clearInterval(silenceTimer)
      silenceTimer = null
    }
    set({ volume: 0, waveform: Array(64).fill(0), isListening: false, micSilent: false, listeningStoppedAt: Date.now() })
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
      }
    }
  }
})
