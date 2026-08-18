import React, { useState, useEffect } from 'react'
import QRCode from 'qrcode'
import { BACKEND_BASE, openExternal } from '../env.js'
import { Icon } from './ui.jsx'

export default function FollowModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('follow') // 'follow' | 'stage'
  const [networkInfo, setNetworkInfo] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    let isMounted = true
    setLoading(true)

    fetch(`${BACKEND_BASE}/api/v1/network/info`)
      .then(res => res.json())
      .then(data => {
        if (!isMounted) return
        setNetworkInfo(data)
        const url = activeTab === 'follow' ? data.follow_url : data.stage_url
        return QRCode.toDataURL(url, {
          width: 240,
          margin: 2,
          color: {
            dark: '#030712',
            light: '#ffffff'
          }
        })
      })
      .then(qr => {
        if (!isMounted) return
        setQrDataUrl(qr)
        setLoading(false)
      })
      .catch(err => {
        console.error('Erreur chargement réseau/QR:', err)
        if (isMounted) setLoading(false)
      })

    return () => { isMounted = false }
  }, [isOpen, activeTab])

  if (!isOpen) return null

  const currentUrl = activeTab === 'follow'
    ? (networkInfo?.follow_url || `${BACKEND_BASE}/follow`)
    : (networkInfo?.stage_url || `${BACKEND_BASE}/stage`)

  const handleCopy = () => {
    navigator.clipboard.writeText(currentUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="vp-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="vp-modal max-w-md w-full p-6 text-center" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-xl">📱</span>
            <h3 className="text-base font-semibold text-text">Écrans Mobiles & Réseau</h3>
          </div>
          <button 
            type="button" 
            className="vp-btn vp-btn--ghost vp-btn--sm text-text-dim hover:text-text"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {/* Sélecteur d'écran */}
        <div className="flex gap-2 p-1 bg-surface-2 rounded-lg mb-4 text-xs">
          <button
            type="button"
            className={`flex-1 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'follow'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-text-dim hover:text-text'
            }`}
            onClick={() => setActiveTab('follow')}
          >
            👥 Assemblée (/follow)
          </button>
          <button
            type="button"
            className={`flex-1 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'stage'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-text-dim hover:text-text'
            }`}
            onClick={() => setActiveTab('stage')}
          >
            🎤 Scène Pasteur (/stage)
          </button>
        </div>

        {/* Conteneur QR Code */}
        <div className="flex flex-col items-center justify-center p-4 bg-surface-2 border border-border rounded-xl mb-4">
          {loading ? (
            <div className="w-[200px] h-[200px] flex items-center justify-center text-xs text-text-dim">
              Génération du QR Code…
            </div>
          ) : qrDataUrl ? (
            <div className="bg-white p-2.5 rounded-lg shadow-md">
              <img src={qrDataUrl} alt="QR Code mobile" className="w-[180px] h-[180px] block" />
            </div>
          ) : (
            <div className="w-[200px] h-[200px] flex items-center justify-center text-xs text-rose-400">
              Impossible de générer le QR Code
            </div>
          )}

          <p className="text-xs text-text-dim mt-3 max-w-[280px]">
            {activeTab === 'follow'
              ? 'Scannez pour suivre les versets en temps réel sur smartphone (connecté au Wi-Fi du culte).'
              : 'Écran retour pour pupitre ou tablette scène avec affichage du verset et du chrono.'}
          </p>
        </div>

        {/* Lien direct et boutons */}
        <div className="flex items-center gap-2 p-2 bg-surface-2 border border-border rounded-lg text-xs font-mono mb-4 text-left">
          <span className="truncate flex-1 text-sky-400 select-all">{currentUrl}</span>
          <button
            type="button"
            className="vp-btn vp-btn--secondary vp-btn--sm flex-shrink-0"
            onClick={handleCopy}
          >
            {copied ? '✅ Copié' : '📋 Copier'}
          </button>
        </div>

        <div className="flex gap-2 justify-end">
          <button
            type="button"
            className="vp-btn vp-btn--ghost vp-btn--sm"
            onClick={() => openExternal(currentUrl)}
          >
            Tester dans le navigateur ↗
          </button>
          <button
            type="button"
            className="vp-btn vp-btn--primary vp-btn--sm"
            onClick={onClose}
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  )
}
