import React, { useCallback, useEffect, useRef, useState } from 'react'
import { BACKEND_BASE, isTauri } from '../env.js'

const VIDEO_SRC = '/media/versepro-launch.mp4'
const POSTER_SRC = '/media/versepro-launch-poster.jpg'
const STILL_SRC = '/media/versepro-launch-still.jpg'
const EXIT_DURATION_MS = 420
const SAFETY_TIMEOUT_MS = 7200
const BACKEND_TIMEOUT_MS = 25000

export default function LaunchIntro({ onDone }) {
  const videoRef = useRef(null)
  const finishingRef = useRef(false)
  const [leaving, setLeaving] = useState(false)
  const [canSkip, setCanSkip] = useState(false)
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
        // Le backend empaqueté charge encore ses modèles locaux.
      }
      if (active) retryTimer = window.setTimeout(probeBackend, 400)
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
    if (mediaComplete && backendReady) finish()
  }, [backendReady, finish, mediaComplete])

  useEffect(() => {
    const skipTimer = window.setTimeout(() => setCanSkip(true), 900)
    const safetyTimer = window.setTimeout(completeMedia, reducedMotion ? 700 : SAFETY_TIMEOUT_MS)
    const onKeyDown = (event) => {
      if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') completeMedia()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.clearTimeout(skipTimer)
      window.clearTimeout(safetyTimer)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [completeMedia, reducedMotion])

  useEffect(() => {
    if (reducedMotion || !videoRef.current) return
    const video = videoRef.current
    // Le son fait partie de l'ouverture dans l'application de bureau. Dans un
    // navigateur, l'autoplay sonore est bloqué : on part muet. Et si la lecture
    // sonore est refusée malgré tout, le filet ci-dessous rejoue en muet.
    video.muted = !isTauri
    const playback = video.play()
    playback?.catch(() => {
      video.muted = true
      video.play().catch(completeMedia)
    })
  }, [completeMedia, reducedMotion])

  return (
    <div
      className={`launch-intro ${leaving ? 'is-leaving' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Ouverture de VersePro"
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
            onEnded={() => setMediaComplete(true)}
            onError={completeMedia}
          />
        )}
      </div>

      {mediaComplete && !backendReady && (
        <span className="launch-intro-status">initialisation du moteur…</span>
      )}

      <button
        type="button"
        className={`launch-intro-skip ${canSkip && !mediaComplete ? 'is-visible' : ''}`}
        onClick={completeMedia}
        aria-label="Passer l’animation d’ouverture"
      >
        passer
      </button>
    </div>
  )
}
