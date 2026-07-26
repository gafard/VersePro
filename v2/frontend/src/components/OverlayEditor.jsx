import React, { useCallback, useEffect, useRef, useState } from 'react'
import { BACKEND_BASE } from '../env.js'
import { useStore } from '../store.js'

// Verset d'essai : celui de la capture d'origine, assez long pour révéler un
// débordement de zone avant le dimanche.
const APERCU = {
  reference: 'Exode 17:11 (LSG)',
  numero: '11',
  texte: "Lorsque Moïse élevait sa main, Israël était le plus fort; et lorsqu'il baissait sa main, Amalek était le plus fort."
}

const ZONES = [
  { cle: 'text', nom: 'Verset' },
  { cle: 'reference', nom: 'Référence' }
]

const POLICES = [
  { valeur: 'sans', nom: 'Sans (Arial)' },
  { valeur: 'display', nom: 'Space Grotesk' },
  { valeur: 'serif', nom: 'Serif (Georgia)' },
  { valeur: 'mono', nom: 'Monospace' }
]

const FAMILLES = {
  sans: 'Arial, Helvetica, sans-serif',
  display: '"Space Grotesk", system-ui, sans-serif',
  serif: 'Georgia, "Times New Roman", serif',
  mono: 'ui-monospace, monospace'
}

const borne = (v, bas, haut) => Math.max(bas, Math.min(haut, v))

export default function OverlayEditor() {
  const { addToast } = useStore()
  const [etat, setEtat] = useState(null)
  const [zones, setZones] = useState(null)
  const [selection, setSelection] = useState('text')
  const [occupe, setOccupe] = useState('')
  const cadreRef = useRef(null)
  const glisseRef = useRef(null)

  const charger = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/status`)
      const d = await r.json()
      setEtat(d)
      setZones(d.zones)
    } catch {
      addToast({ message: 'Habillage : serveur injoignable', kind: 'error' })
    }
  }, [addToast])

  useEffect(() => { charger() }, [charger])

  // ── Import du PNG ──────────────────────────────────────────────────────────
  const importer = async (fichier) => {
    if (!fichier) return
    if (!/\.png$/i.test(fichier.name) && fichier.type !== 'image/png') {
      addToast({ message: 'Un PNG est attendu (fond transparent conseillé)', kind: 'error' })
      return
    }
    setOccupe('import')
    try {
      const dataUrl = await new Promise((resoudre, rejeter) => {
        const lecteur = new FileReader()
        lecteur.onload = () => resoudre(lecteur.result)
        lecteur.onerror = () => rejeter(new Error('lecture impossible'))
        lecteur.readAsDataURL(fichier)
      })
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: dataUrl })
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      setEtat((e) => ({ ...(e || {}), ...d }))
      addToast({ message: `Habillage importé (${d.width}×${d.height})`, kind: 'success' })
    } catch (err) {
      addToast({ message: `Import impossible : ${err.message}`, kind: 'error', duration: 7000 })
    } finally {
      setOccupe('')
    }
  }

  const supprimer = async () => {
    setOccupe('suppression')
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/image`, { method: 'DELETE' })
      setEtat({ ...(await r.json()), zones })
      addToast({ message: "Habillage retiré : l'écran revient au style choisi", kind: 'success' })
    } finally {
      setOccupe('')
    }
  }

  // ── Glisser-déposer des zones ──────────────────────────────────────────────
  const demarrerGlisse = (evenement, cle, mode) => {
    evenement.preventDefault()
    evenement.stopPropagation()
    setSelection(cle)
    const cadre = cadreRef.current?.getBoundingClientRect()
    if (!cadre) return
    glisseRef.current = {
      cle, mode, cadre,
      departX: evenement.clientX,
      departY: evenement.clientY,
      zone: { ...zones[cle] }
    }
    evenement.currentTarget.setPointerCapture?.(evenement.pointerId)
  }

  useEffect(() => {
    const bouger = (evenement) => {
      const g = glisseRef.current
      if (!g) return
      const dx = ((evenement.clientX - g.departX) / g.cadre.width) * 100
      const dy = ((evenement.clientY - g.departY) / g.cadre.height) * 100
      setZones((precedent) => {
        const z = { ...precedent[g.cle] }
        if (g.mode === 'move') {
          z.x = borne(g.zone.x + dx, -10, 110)
          z.y = borne(g.zone.y + dy, -10, 110)
        } else {
          z.w = borne(g.zone.w + dx, 3, 130)
          z.h = borne(g.zone.h + dy, 2, 130)
        }
        return { ...precedent, [g.cle]: z }
      })
    }
    const relacher = () => { glisseRef.current = null }
    window.addEventListener('pointermove', bouger)
    window.addEventListener('pointerup', relacher)
    return () => {
      window.removeEventListener('pointermove', bouger)
      window.removeEventListener('pointerup', relacher)
    }
  }, [])

  const majZone = (cle, champ, valeur) =>
    setZones((p) => ({ ...p, [cle]: { ...p[cle], [champ]: valeur } }))

  const enregistrer = async () => {
    setOccupe('enregistrement')
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overlay_zones: zones })
      })
      if (!r.ok) throw new Error(`Erreur ${r.status}`)
      addToast({ message: 'Zones enregistrées — visibles à la prochaine projection', kind: 'success' })
      charger()
    } catch (err) {
      addToast({ message: `Enregistrement impossible : ${err.message}`, kind: 'error' })
    } finally {
      setOccupe('')
    }
  }

  if (!zones) return <p className="settings-muted-note">Chargement de l'habillage…</p>

  const zoneActive = zones[selection]
  const installe = Boolean(etat?.installed)

  return (
    <div className="overlay-editor">
      <div className="overlay-actions">
        <label className="vp-btn vp-btn--sm">
          {installe ? "Remplacer le PNG" : "Importer un PNG"}
          <input
            type="file" accept="image/png" hidden
            onChange={(e) => { importer(e.target.files?.[0]); e.target.value = '' }}
          />
        </label>
        {installe && (
          <button className="vp-btn vp-btn--sm" onClick={supprimer} disabled={occupe === 'suppression'}>
            Retirer
          </button>
        )}
        <span className="settings-muted-note" style={{ margin: 0 }}>
          {occupe === 'import' ? 'import en cours…'
            : installe ? `${etat.width}×${etat.height} · ${Math.round(etat.bytes / 1024)} Ko`
              : 'aucun habillage : l’écran garde le style choisi plus haut'}
        </span>
      </div>

      {/* Cadre 16:9 : ce qu'on voit ici est ce que la projection affichera. */}
      <div className="overlay-frame" ref={cadreRef}>
        {installe && (
          <img className="overlay-frame-img" alt=""
            src={`${BACKEND_BASE}/overlay.png?v=${etat.updated_at}`} />
        )}
        {ZONES.map(({ cle, nom }) => {
          const z = zones[cle]
          const estTexte = cle === 'text'
          return (
            <div
              key={cle}
              className={`overlay-box ${selection === cle ? 'is-selected' : ''}`}
              style={{
                left: `${z.x}%`, top: `${z.y}%`, width: `${z.w}%`, height: `${z.h}%`,
                justifyContent: z.align === 'center' ? 'center' : z.align === 'right' ? 'flex-end' : 'flex-start',
                alignItems: z.valign === 'middle' ? 'center' : z.valign === 'bottom' ? 'flex-end' : 'flex-start'
              }}
              onPointerDown={(e) => demarrerGlisse(e, cle, 'move')}
            >
              <span
                className="overlay-box-text"
                style={{
                  // La taille est en vh à la projection : dans l'aperçu, on la
                  // rapporte à la hauteur du cadre pour voir la vraie échelle.
                  fontSize: `${z.size}cqh`,
                  lineHeight: z.line,
                  color: z.color,
                  fontWeight: z.weight,
                  textAlign: z.align,
                  fontFamily: FAMILLES[z.font] || FAMILLES.sans
                }}
              >
                {estTexte ? <><sup className="overlay-vnum">{APERCU.numero}</sup>{APERCU.texte}</> : APERCU.reference}
              </span>
              <span className="overlay-box-tag">{nom}</span>
              <span
                className="overlay-handle"
                onPointerDown={(e) => demarrerGlisse(e, cle, 'resize')}
              />
            </div>
          )
        })}
      </div>

      <div className="overlay-tabs">
        {ZONES.map(({ cle, nom }) => (
          <button
            key={cle}
            className={`vp-btn vp-btn--sm ${selection === cle ? 'vp-btn--primary' : ''}`}
            onClick={() => setSelection(cle)}
          >{nom}</button>
        ))}
      </div>

      <div className="settings-form-grid overlay-controls">
        <label>
          <small>Taille (% de la hauteur)</small>
          <input type="range" min="0.8" max="14" step="0.1" value={zoneActive.size}
            onChange={(e) => majZone(selection, 'size', Number(e.target.value))} />
          <span className="settings-muted-note">{zoneActive.size.toFixed(1)}</span>
        </label>
        <label>
          <small>Couleur</small>
          <input type="color" value={zoneActive.color}
            onChange={(e) => majZone(selection, 'color', e.target.value)} />
        </label>
        <label>
          <small>Police</small>
          <select value={zoneActive.font} onChange={(e) => majZone(selection, 'font', e.target.value)}>
            {POLICES.map((p) => <option key={p.valeur} value={p.valeur}>{p.nom}</option>)}
          </select>
        </label>
        <label>
          <small>Graisse</small>
          <select value={zoneActive.weight} onChange={(e) => majZone(selection, 'weight', Number(e.target.value))}>
            <option value={400}>Normale</option>
            <option value={500}>Moyenne</option>
            <option value={600}>Demi-grasse</option>
            <option value={700}>Grasse</option>
          </select>
        </label>
        <label>
          <small>Alignement horizontal</small>
          <select value={zoneActive.align} onChange={(e) => majZone(selection, 'align', e.target.value)}>
            <option value="left">Gauche</option>
            <option value="center">Centré</option>
            <option value="right">Droite</option>
          </select>
        </label>
        <label>
          <small>Alignement vertical</small>
          <select value={zoneActive.valign} onChange={(e) => majZone(selection, 'valign', e.target.value)}>
            <option value="top">Haut</option>
            <option value="middle">Milieu</option>
            <option value="bottom">Bas</option>
          </select>
        </label>
        <label>
          <small>Interligne</small>
          <input type="range" min="0.9" max="2" step="0.02" value={zoneActive.line}
            onChange={(e) => majZone(selection, 'line', Number(e.target.value))} />
          <span className="settings-muted-note">{zoneActive.line.toFixed(2)}</span>
        </label>
      </div>

      <button className="vp-btn vp-btn--primary vp-btn--sm" onClick={enregistrer} disabled={occupe === 'enregistrement'}>
        {occupe === 'enregistrement' ? 'Enregistrement…' : 'Enregistrer les zones'}
      </button>
      <span className="settings-muted-note">
        Déplacez une zone en la faisant glisser ; la poignée en bas à droite la redimensionne.
        Les positions sont en pourcentages du cadre : le réglage fait ici tient du 720p au 4K.
      </span>
    </div>
  )
}
