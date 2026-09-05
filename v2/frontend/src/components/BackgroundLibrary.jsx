import React, { useEffect, useRef, useState } from 'react'
import { BACKEND_BASE } from '../env.js'

const assetUrl = (url) => `${BACKEND_BASE}${url || ''}`

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 20h14" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="m19 6-1 14H6L5 6" />
    </svg>
  )
}

export default function BackgroundLibrary({ form, updateField, theme, addToast }) {
  const inputRef = useRef(null)
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/backgrounds`)
      if (!response.ok) throw new Error('Bibliothèque indisponible')
      const data = await response.json()
      setAssets(data.assets || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Impossible de charger les fonds')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const upload = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      addToast?.({ message: 'Utilisez une image PNG, JPEG ou WebP', kind: 'error' })
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      addToast?.({ message: 'Le fond dépasse la limite de 20 Mo', kind: 'error' })
      return
    }
    setUploading(true)
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result)
        reader.onerror = () => reject(new Error('Lecture du fichier impossible'))
        reader.readAsDataURL(file)
      })
      const response = await fetch(`${BACKEND_BASE}/api/v1/backgrounds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data, name: file.name.replace(/\.[^.]+$/, '') })
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Import impossible')
      setAssets((current) => [result, ...current.filter((asset) => asset.id !== result.id)])
      updateField('background_asset', result.id)
      updateField('background_enabled', true)
      setError('')
      addToast?.({ message: 'Fond ajouté à la bibliothèque', kind: 'success' })
    } catch (err) {
      setError(err.message || 'Import impossible')
      addToast?.({ message: err.message || 'Import impossible', kind: 'error' })
    } finally {
      setUploading(false)
    }
  }

  const remove = async () => {
    if (!form.background_asset) return
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/backgrounds/${form.background_asset}`, {
        method: 'DELETE'
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Suppression impossible')
      setAssets(result.assets || [])
      updateField('background_asset', '')
      updateField('background_enabled', false)
      addToast?.({ message: 'Fond supprimé', kind: 'success' })
    } catch (err) {
      addToast?.({ message: err.message || 'Suppression impossible', kind: 'error' })
    }
  }

  const setFocalPoint = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    updateField('background_position_x', Math.round((event.clientX - rect.left) / rect.width * 100))
    updateField('background_position_y', Math.round((event.clientY - rect.top) / rect.height * 100))
  }

  const selected = assets.find((asset) => asset.id === form.background_asset)
  const incompatible = ['broadcast', 'confidence'].includes(theme)

  return (
    <div className="background-library">
      <input ref={inputRef} className="background-file-input" type="file" accept="image/png,image/jpeg,image/webp" onChange={upload} />

      <div className="background-library-head">
        <div>
          <strong>Bibliothèque locale</strong>
          <span>PNG, JPEG ou WebP, conservé sur ce poste.</span>
        </div>
        <button type="button" className="vp-btn vp-btn--ghost" onClick={() => inputRef.current?.click()} disabled={uploading}>
          <UploadIcon /> {uploading ? 'Import…' : 'Ajouter'}
        </button>
      </div>

      {incompatible && (
        <div className="background-mode-note">
          Ce fond est prêt, mais reste masqué avec {theme === 'broadcast' ? 'un lower-third transparent' : 'le retour scène'}.
        </div>
      )}
      {error && <span className="settings-error-note">{error}</span>}

      <div className="background-assets" aria-label="Fonds disponibles">
        {loading && <div className="background-empty">Chargement…</div>}
        {!loading && !assets.length && (
          <div className="background-empty">Ajoutez une image pour créer votre premier fond plein écran.</div>
        )}
        {assets.map((asset) => (
          <button
            type="button"
            key={asset.id}
            className={`background-asset${form.background_asset === asset.id ? ' is-selected' : ''}`}
            onClick={() => {
              updateField('background_asset', asset.id)
              updateField('background_enabled', true)
            }}
            aria-pressed={form.background_asset === asset.id}
            title={`${asset.name} · ${asset.width} × ${asset.height}`}
          >
            <img src={assetUrl(asset.thumbnail_url)} alt="" />
            <span>{asset.name}</span>
          </button>
        ))}
      </div>

      <div className="settings-row background-enable-row">
        <div className="settings-row-info">
          <span className="settings-row-label">Activer le fond</span>
          <span className="settings-row-desc">Visible sur les thèmes plein écran et la sortie NDI.</span>
        </div>
        <div className="settings-row-control">
          <label className="settings-switch">
            <input
              type="checkbox"
              checked={Boolean(form.background_enabled)}
              disabled={!form.background_asset}
              onChange={(event) => updateField('background_enabled', event.target.checked)}
            />
            <span />
          </label>
        </div>
      </div>

      {selected && (
        <div className="background-workbench">
          <button
            type="button"
            className="background-focal"
            onClick={setFocalPoint}
            title="Cliquez sur le sujet principal de l'image"
            aria-label="Choisir le point focal"
          >
            <img
              src={assetUrl(selected.image_url)}
              alt="Aperçu du fond sélectionné"
              style={{
                objectFit: form.background_fit || 'cover',
                objectPosition: `${form.background_position_x}% ${form.background_position_y}%`,
                filter: form.background_blur ? `blur(${form.background_blur}px)` : 'none'
              }}
            />
            <span
              className="background-focal-marker"
              style={{ left: `${form.background_position_x}%`, top: `${form.background_position_y}%` }}
            />
            <span className="background-focal-label">Point focal</span>
          </button>

          <div className="background-controls">
            <div className="background-control">
              <label>Cadrage</label>
              <div className="settings-segmented-sv">
                {[
                  ['cover', 'Remplir'], ['contain', 'Contenir'], ['fill', 'Étirer']
                ].map(([value, label]) => (
                  <button key={value} type="button" className={form.background_fit === value ? 'is-active' : ''} onClick={() => updateField('background_fit', value)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="background-control background-color-control">
              <label htmlFor="background-overlay-color">Voile</label>
              <input id="background-overlay-color" type="color" value={form.background_overlay_color} onChange={(event) => updateField('background_overlay_color', event.target.value)} />
            </div>

            <div className="background-control">
              <label htmlFor="background-overlay-opacity">Contraste <span>{Math.round(form.background_overlay_opacity * 100)}%</span></label>
              <input id="background-overlay-opacity" type="range" min="0" max="0.9" step="0.01" value={form.background_overlay_opacity} onChange={(event) => updateField('background_overlay_opacity', Number(event.target.value))} />
            </div>

            <div className="background-control">
              <label htmlFor="background-blur">Flou <span>{form.background_blur}px</span></label>
              <input id="background-blur" type="range" min="0" max="20" step="1" value={form.background_blur} onChange={(event) => updateField('background_blur', Number(event.target.value))} />
            </div>

            <button type="button" className="background-delete" onClick={remove} title="Supprimer ce fond">
              <TrashIcon /><span>Supprimer</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
