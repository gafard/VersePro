import React, { useCallback, useEffect, useRef, useState } from 'react'
import { BACKEND_BASE, isTauri } from '../env.js'

const VIDEO_SRC = '/media/versepro-launch.mp4'
const POSTER_SRC = '/media/versepro-launch-poster.jpg'
const STILL_SRC = '/media/versepro-launch-still.jpg'
const EXIT_DURATION_MS = 300
const SAFETY_TIMEOUT_MS = 5000
const BACKEND_TIMEOUT_MS = 3500

export default function LaunchIntro({ onDone }) {
  const videoRef = useRef(null)
  const finishingRef = useRef(false)
  const [leaving, setLeaving] = useState(false)
  const [canSkip, setCanSkip] = useState(true)
  const [reducedMotion] = useState(() => (
    typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  ))
  const [mediaComplete, setMediaComplete] = useState(reducedMotion)
  const [showStill, setShowStill] = useState(reducedMotion)
  const [backendReady, setBackendReady] = useState(!isTauri)

  const finish = useCallback(() => {
    if (finishingRef.current) return
    finishingRef.current = true
    setLeaving(true)
    window.setTimeout(onDone, EXIT_DURATION_MS)
  }, [onDone])

  const completeMedia = useCallback(() => {
    const video = videoRef.current
    if (video && !video.ended) video.pause()
    setShowStill(true)
    setMediaComplete(true)
  }, [])

  useEffect(() => {
    if (!isTauri) return
    let active = true
    let retryTimer = null

    const probeBackend = async () => {
      try {
        const response = await fetch(`${BACKEND_BASE}/health`, { cache: 'no-store' })
        if (response.ok) {
          if (active) setBackendReady(true)
          return
        }
      } catch {
        // Le backend empaqueté charge en arrière-plan
      }
      if (active) retryTimer = window.setTimeout(probeBackend, 350)
    }

    probeBackend()
    const hardTimeout = window.setTimeout(() => {
      if (active) setBackendReady(true)
    }, BACKEND_TIMEOUT_MS)

    return () => {
      active = false
      window.clearTimeout(retryTimer)
      window.clearTimeout(hardTimeout)
    }
  }, [])

  useEffect(() => {
    if (mediaComplete && backendReady) {
      finish()
      return
    }
    if (mediaComplete) {
      const graceTimer = window.setTimeout(finish, 1200)
      return () => window.clearTimeout(graceTimer)
    }
  }, [backendReady, finish, mediaComplete])

  useEffect(() => {
    const skipTimer = window.setTimeout(() => setCanSkip(true), 400)
    const safetyTimer = window.setTimeout(() => {
      completeMedia()
      finish()
    }, reducedMotion ? 500 : SAFETY_TIMEOUT_MS)

    const onKeyDown = (event) => {
      if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') finish()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.clearTimeout(skipTimer)
      window.clearTimeout(safetyTimer)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [completeMedia, finish, reducedMotion])

  useEffect(() => {
    if (reducedMotion || !videoRef.current) return
    const video = videoRef.current
    video.muted = !isTauri
    const playback = video.play()
    playback?.catch(() => {
      video.muted = true
      video.play().catch(() => {
        completeMedia()
        finish()
      })
    })
  }, [completeMedia, finish, reducedMotion])

  return (
    <div
      className={`launch-intro ${leaving ? 'is-leaving' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Ouverture de VersePro"
      onClick={finish}
    >
      <div className="launch-intro-media" aria-hidden="true">
        {showStill ? (
          <img src={STILL_SRC} alt="" />
        ) : (
          <video
            ref={videoRef}
            src={VIDEO_SRC}
            poster={POSTER_SRC}
            autoPlay
            muted={!isTauri}
            playsInline
            preload="auto"
            onEnded={() => {
              setMediaComplete(true)
              finish()
            }}
            onError={() => {
              completeMedia()
              finish()
            }}
          />
        )}
      </div>

      <button
        type="button"
        className={`launch-intro-skip ${canSkip ? 'is-visible' : ''}`}
        onClick={(e) => {
          e.stopPropagation()
          finish()
        }}
        aria-label="Passer l’animation d’ouverture"
      >
        passer
      </button>
    </div>
  )
}
