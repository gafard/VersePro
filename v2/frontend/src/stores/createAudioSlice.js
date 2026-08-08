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
      }
    }
  }
})
