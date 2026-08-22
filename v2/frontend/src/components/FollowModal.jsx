import React, { useState, useEffect } from 'react'
import QRCode from 'qrcode'
import { BACKEND_BASE, openExternal } from '../env.js'
import { Icon } from './ui.jsx'

export default function FollowModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('follow') // 'follow' | 'stage'
  const [networkInfo, setNetworkInfo] = useState(null)
  const [selectedIp, setSelectedIp] = useState('')
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
        const currentIp = selectedIp || data.local_ip || '127.0.0.1'
        if (!selectedIp && data.local_ip) {
          setSelectedIp(data.local_ip)
        }
        const port = data.port || 17871
        const targetPath = activeTab === 'follow' ? '/follow' : '/stage'
        const url = `http://${currentIp}:${port}${targetPath}`

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
  }, [isOpen, activeTab, selectedIp])

  if (!isOpen) return null

  const port = networkInfo?.port || 17871
  const activeIp = selectedIp || networkInfo?.local_ip || '127.0.0.1'
  const currentUrl = `http://${activeIp}:${port}/${activeTab}`

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

        {/* Avertissement si IP loopback 127.0.0.1 */}
        {activeIp.startsWith('127.') && (
          <div className="p-2.5 mb-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300 text-left leading-relaxed">
            ⚠️ <strong>Non connecté au Wi-Fi :</strong> L'ordinateur utilise l'adresse locale <code>127.0.0.1</code>. Connectez cet ordinateur et votre smartphone au <strong>même réseau Wi-Fi</strong> pour que le scan fonctionne.
          </div>
        )}

        {/* Sélecteur d'interface IP si plusieurs réseaux disponibles */}
        {networkInfo?.available_ips && networkInfo.available_ips.length > 1 && (
          <div className="flex items-center justify-between gap-2 p-2 bg-surface-2 border border-border rounded-lg mb-3 text-xs">
            <span className="text-text-dim text-[11px]">Réseau Wi-Fi / IP :</span>
            <select
              className="bg-surface-3 text-text border border-border rounded px-2 py-1 text-xs font-mono outline-none"
              value={selectedIp}
              onChange={(e) => setSelectedIp(e.target.value)}
            >
              {networkInfo.available_ips.map((ip) => (
                <option key={ip} value={ip}>{ip}</option>
              ))}
            </select>
          </div>
        )}

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
              ? 'Scannez pour suivre les versets en temps réel sur smartphone (connecté au même Wi-Fi).'
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
