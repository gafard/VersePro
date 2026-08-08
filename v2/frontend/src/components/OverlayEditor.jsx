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

// Coins dans le sens horaire depuis le haut-gauche, comme la géométrie du
// serveur : l'ordre du tableau EST celui du contour tracé.
const COINS = [
  { index: 0, nom: 'Haut gauche' },
  { index: 1, nom: 'Haut droit' },
  { index: 2, nom: 'Bas droit' },
  { index: 3, nom: 'Bas gauche' }
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

// Jumeau de shape_geometry.py et du tracé de la page de projection : mêmes
// angles, même ordre, même nombre de segments. Trois copies, une seule
// géométrie — c'est le prix à payer pour que l'aperçu, l'écran et NDI
// s'accordent au pixel près.
const SEGMENTS_ARC = 10
function contourForme(L, H, coins) {
  const limite = Math.max(0, Math.min(L, H) / 2)
  const r = [], m = []
  for (let i = 0; i < 4; i++) {
    const c = (coins && coins[i]) || {}
    r.push(Math.max(0, Math.min(limite, Number(c.r) || 0)))
    m.push(['out', 'in', 'cut'].includes(c.mode) ? c.mode : 'out')
  }
  const P = Math.PI
  const sommets = [[0, 0], [L, 0], [L, H], [0, H]]
  const entrees = [[0, r[0]], [L - r[1], 0], [L, H - r[2]], [r[3], H]]
  const sorties = [[r[0], 0], [L, r[1]], [L - r[2], H], [0, H - r[3]]]
  const centres = [[r[0], r[0]], [L - r[1], r[1]], [L - r[2], H - r[2]], [r[3], H - r[3]]]
  const angles = [[P, 1.5 * P], [1.5 * P, 2 * P], [0, 0.5 * P], [0.5 * P, P]]
  const rentrants = [[0.5 * P, 0], [P, 0.5 * P], [1.5 * P, P], [0, -0.5 * P]]
  const pts = []
  const arc = (centre, rayon, a, b) => {
    for (let i = 0; i <= SEGMENTS_ARC; i++) {
      const t = a + (b - a) * i / SEGMENTS_ARC
      pts.push([centre[0] + rayon * Math.cos(t), centre[1] + rayon * Math.sin(t)])
    }
  }
  for (let i = 0; i < 4; i++) {
    if (r[i] <= 0) { pts.push(sommets[i]); continue }
    pts.push(entrees[i])
    if (m[i] === 'in') arc(sommets[i], r[i], rentrants[i][0], rentrants[i][1])
    else if (m[i] !== 'cut') arc(centres[i], r[i], angles[i][0], angles[i][1])
    pts.push(sorties[i])
  }
  return pts
}

const DEFAUT_ZONES = {
  text: { x: 6.5, y: 81.0, w: 87.0, h: 13.5, size: 5.0, color: '#1d2b63', align: 'left', valign: 'middle', weight: 700, font: 'sans', line: 1.16 },
  reference: { x: 63.5, y: 74.5, w: 32.0, h: 5.4, size: 2.8, color: '#ffffff', align: 'center', valign: 'middle', weight: 700, font: 'sans', line: 1.2 }
}

export default function OverlayEditor() {
  const addToast = useStore(s => s.addToast)
  const [etat, setEtat] = useState(null)
  const [zones, setZones] = useState(DEFAUT_ZONES)
  const [formes, setFormes] = useState([])
  // Sélection : 'text' / 'reference' pour une zone, ou l'indice d'une forme.
  const [selection, setSelection] = useState('text')
  const [occupe, setOccupe] = useState('')
  const cadreRef = useRef(null)
  const glisseRef = useRef(null)

  const [presets, setPresets] = useState([])
  const [nomPreset, setNomPreset] = useState('')
  const [categoriePreset, setCategoriePreset] = useState('Bandeaux')

  const chargerPresets = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/library`)
      setPresets((await r.json()).presets || [])
    } catch { /* la bibliothèque reste vide, l'éditeur fonctionne quand même */ }
  }, [])

  const charger = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/status`)
      const d = await r.json()
      setEtat(d)
      if (d.zones) setZones(d.zones)
      setFormes(d.shapes || [])
      chargerPresets()
    } catch {
      /* si le serveur met quelques secondes à répondre, les zones par défaut restent actives */
    }
  }, [chargerPresets])

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

  // ── Glisser-déposer (zones de texte ET formes) ─────────────────────────────
  // `cible` vaut 'text' / 'reference' pour une zone, ou l'indice d'une forme.
  const demarrerGlisse = (evenement, cible, mode) => {
    evenement.preventDefault()
    evenement.stopPropagation()
    setSelection(cible)
    const cadre = cadreRef.current?.getBoundingClientRect()
    if (!cadre) return
    const depart = typeof cible === 'number' ? formes[cible] : zones[cible]
    glisseRef.current = {
      cible, mode, cadre,
      departX: evenement.clientX,
      departY: evenement.clientY,
      boite: { ...depart }
    }
    evenement.currentTarget.setPointerCapture?.(evenement.pointerId)
  }

  useEffect(() => {
    const bouger = (evenement) => {
      const g = glisseRef.current
      if (!g) return
      const dx = ((evenement.clientX - g.departX) / g.cadre.width) * 100
      const dy = ((evenement.clientY - g.departY) / g.cadre.height) * 100
      const deplace = (b) => {
        const n = { ...b }
        if (g.mode === 'move') {
          n.x = borne(g.boite.x + dx, -10, 110)
          n.y = borne(g.boite.y + dy, -10, 110)
        } else {
          n.w = borne(g.boite.w + dx, 1, 130)
          n.h = borne(g.boite.h + dy, 1, 130)
        }
        return n
      }
      if (typeof g.cible === 'number') {
        setFormes((p) => p.map((f, i) => (i === g.cible ? deplace(f) : f)))
      } else {
        setZones((p) => ({ ...p, [g.cible]: deplace(p[g.cible]) }))
      }
    }
    const relacher = () => { glisseRef.current = null }
    window.addEventListener('pointermove', bouger)
    window.addEventListener('pointerup', relacher)
    return () => {
      window.removeEventListener('pointermove', bouger)
      window.removeEventListener('pointerup', relacher)
    }
  }, [formes, zones])

  // ── Formes ─────────────────────────────────────────────────────────────────
  const majForme = (index, champ, valeur) =>
    setFormes((p) => p.map((f, i) => (i === index ? { ...f, [champ]: valeur } : f)))

  const coinsDe = (f) =>
    (f.corners && f.corners.length === 4)
      ? f.corners
      : Array.from({ length: 4 }, () => ({ r: f.radius || 0, mode: 'out' }))

  const majCoin = (indexForme, indexCoin, champ, valeur) =>
    setFormes((p) => p.map((f, i) => {
      if (i !== indexForme) return f
      const coins = coinsDe(f).map((c, k) => (k === indexCoin ? { ...c, [champ]: valeur } : c))
      return { ...f, corners: coins }
    }))

  const uniformiserCoins = (indexForme) =>
    setFormes((p) => p.map((f, i) => {
      if (i !== indexForme) return f
      const premier = coinsDe(f)[0]
      return { ...f, corners: Array.from({ length: 4 }, () => ({ ...premier })) }
    }))

  const ajouterForme = () => {
    setFormes((p) => {
      if (p.length >= 12) {
        addToast({ message: 'Douze formes au maximum', kind: 'error' })
        return p
      }
      setSelection(p.length)
      return [...p, { x: 20, y: 40, w: 40, h: 12, fill: '#ffffff', opacity: 1, radius: 1.5 }]
    })
  }

  const supprimerForme = (index) => {
    setFormes((p) => p.filter((_, i) => i !== index))
    setSelection('text')
  }

  // L'ordre du tableau EST l'ordre d'empilement : monter une forme, c'est la
  // faire passer devant celle qui la suit.
  const deplacerForme = (index, sens) => {
    setFormes((p) => {
      const cible = index + sens
      if (cible < 0 || cible >= p.length) return p
      const copie = [...p]
      ;[copie[index], copie[cible]] = [copie[cible], copie[index]]
      setSelection(cible)
      return copie
    })
  }

  const majZone = (cle, champ, valeur) =>
    setZones((p) => ({ ...p, [cle]: { ...p[cle], [champ]: valeur } }))

  const enregistrer = async () => {
    setOccupe('enregistrement')
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overlay_zones: zones, overlay_shapes: formes })
      })
      if (!r.ok) throw new Error(`Erreur ${r.status}`)
      addToast({ message: 'Habillage enregistré — visible à la prochaine projection', kind: 'success' })
      charger()
    } catch (err) {
      addToast({ message: `Enregistrement impossible : ${err.message}`, kind: 'error' })
    } finally {
      setOccupe('')
    }
  }

  // ── Bibliothèque ───────────────────────────────────────────────────────────
  const enregistrerSous = async () => {
    const nom = nomPreset.trim()
    if (!nom) { addToast({ message: 'Donnez un nom à cet habillage', kind: 'error' }); return }
    setOccupe('bibliotheque')
    try {
      // On envoie l'état de l'éditeur, pas celui de la base : ce que l'opérateur
      // voit à l'écran est ce qui part dans la bibliothèque.
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/library`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nom, category: categoriePreset.trim() || 'Mes habillages', zones, shapes: formes })
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      // On boucle explicitement : enregistrer ne projette pas, il faut encore
      // choisir l'habillage dans la liste des styles. Sans ce rappel,
      // l'opérateur croit avoir terminé et ne voit rien changer à l'écran.
      addToast({
        message: `« ${d.name} » enregistré dans ${d.category} — choisissez-le dans « Style de Lower-Third » pour le projeter`,
        kind: 'success',
        duration: 8000
      })
      setNomPreset('')
      chargerPresets()
    } catch (err) {
      addToast({ message: `Enregistrement impossible : ${err.message}`, kind: 'error' })
    } finally { setOccupe('') }
  }

  const appliquerPreset = async (slug, nom) => {
    setOccupe('bibliotheque')
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/library/${slug}/apply`, { method: 'POST' })
      if (!r.ok) throw new Error(`Erreur ${r.status}`)
      addToast({ message: `« ${nom} » chargé dans l'éditeur`, kind: 'success' })
      charger()
    } catch (err) {
      addToast({ message: `Chargement impossible : ${err.message}`, kind: 'error' })
    } finally { setOccupe('') }
  }

  const supprimerPreset = async (slug) => {
    setOccupe('bibliotheque')
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/overlay/library/${slug}`, { method: 'DELETE' })
      setPresets((await r.json()).presets || [])
    } finally { setOccupe('') }
  }

  if (!zones) return <p className="settings-muted-note">Chargement de l'habillage…</p>

  const zoneActive = typeof selection === 'string' ? zones[selection] : null
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
        {/* Formes sous les textes, dans l'ordre du tableau : ce qu'on voit ici
            est exactement l'empilement de la projection. */}
        {formes.map((f, i) => (
          <div
            key={i}
            className={`overlay-box overlay-box--shape ${selection === i ? 'is-selected' : ''}`}
            style={{ left: `${f.x}%`, top: `${f.y}%`, width: `${f.w}%`, height: `${f.h}%` }}
            onPointerDown={(e) => demarrerGlisse(e, i, 'move')}
          >
            {/* Tracé SVG et non border-radius : l'aperçu doit montrer les coins
                creusés et biseautés, sans quoi il mentirait sur le résultat. */}
            <svg className="overlay-shape-svg" viewBox={`0 0 ${f.w * 16} ${f.h * 9}`} preserveAspectRatio="none">
              <polygon
                points={contourForme(f.w * 16, f.h * 9,
                  coinsDe(f).map((c) => ({ r: (c.r || 0) * 9, mode: c.mode })))
                  .map((p) => p.join(',')).join(' ')}
                fill={f.fill}
                opacity={f.opacity}
              />
            </svg>
            <span className="overlay-box-tag">Forme {i + 1}</span>
            <span className="overlay-handle" onPointerDown={(e) => demarrerGlisse(e, i, 'resize')} />
          </div>
        ))}
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
        {formes.map((_, i) => (
          <button
            key={i}
            className={`vp-btn vp-btn--sm ${selection === i ? 'vp-btn--primary' : ''}`}
            onClick={() => setSelection(i)}
          >Forme {i + 1}</button>
        ))}
        <button className="vp-btn vp-btn--sm" onClick={ajouterForme}>+ Forme</button>
      </div>

      {typeof selection === 'number' && formes[selection] && (
        <div className="settings-form-grid overlay-controls">
          <label>
            <small>Couleur de remplissage</small>
            <input type="color" value={formes[selection].fill}
              onChange={(e) => majForme(selection, 'fill', e.target.value)} />
          </label>
          <label>
            <small>Opacité</small>
            <input type="range" min="0" max="1" step="0.01" value={formes[selection].opacity}
              onChange={(e) => majForme(selection, 'opacity', Number(e.target.value))} />
            <span className="settings-muted-note">{Math.round(formes[selection].opacity * 100)} %</span>
          </label>
          <label className="overlay-corners">
            <small>Coins — chacun son rayon et sa forme</small>
            <div className="overlay-corner-grid">
              {COINS.map(({ index, nom }) => {
                const coin = (formes[selection].corners || [])[index] || { r: formes[selection].radius, mode: 'out' }
                return (
                  <div key={index} className="overlay-corner">
                    <small>{nom}</small>
                    <input type="range" min="0" max="20" step="0.1" value={coin.r}
                      onChange={(e) => majCoin(selection, index, 'r', Number(e.target.value))} />
                    <select value={coin.mode} onChange={(e) => majCoin(selection, index, 'mode', e.target.value)}>
                      <option value="out">Arrondi</option>
                      <option value="in">Creusé</option>
                      <option value="cut">Biseauté</option>
                    </select>
                  </div>
                )
              })}
            </div>
            <button className="vp-btn vp-btn--sm" onClick={() => uniformiserCoins(selection)}>
              Appliquer le premier coin aux quatre
            </button>
          </label>
          <label>
            <small>Ordre et suppression</small>
            <span className="overlay-tabs">
              <button className="vp-btn vp-btn--sm" onClick={() => deplacerForme(selection, -1)}>↓ Dessous</button>
              <button className="vp-btn vp-btn--sm" onClick={() => deplacerForme(selection, 1)}>↑ Dessus</button>
              <button className="vp-btn vp-btn--sm vp-btn--danger" onClick={() => supprimerForme(selection)}>Supprimer</button>
            </span>
          </label>
        </div>
      )}

      {typeof selection === 'string' && (
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
      )}

      <button className="vp-btn vp-btn--primary vp-btn--sm" onClick={enregistrer} disabled={occupe === 'enregistrement'}>
        {occupe === 'enregistrement' ? 'Enregistrement…' : 'Enregistrer l\'habillage'}
      </button>
      <span className="settings-muted-note">
        Déplacez une zone en la faisant glisser ; la poignée en bas à droite la redimensionne.
        Les positions sont en pourcentages du cadre : le réglage fait ici tient du 720p au 4K.
      </span>

      {/* Bibliothèque : sans elle, l'habillage est unique et essayer une
          variante détruit la précédente. */}
      <div className="settings-divider">
        <div className="settings-card-head">
          <div>
            <small>Bibliothèque d'habillages</small>
            <p>
              Enregistrez celui-ci sous un nom : il rejoindra la liste des styles,
              rangé dans sa catégorie, et restera disponible pour les cultes suivants.
            </p>
          </div>
        </div>
        <div className="settings-two-cols">
          <label>
            <small>Nom</small>
            <input value={nomPreset} placeholder="ex. Bandeau dimanche"
              onChange={(e) => setNomPreset(e.target.value)} />
          </label>
          <label>
            <small>Catégorie</small>
            <input value={categoriePreset} list="overlay-categories"
              onChange={(e) => setCategoriePreset(e.target.value)} />
            <datalist id="overlay-categories">
              <option value="Bandeaux" />
              <option value="Annonces" />
              <option value="Plein écran" />
              <option value="Fêtes" />
            </datalist>
          </label>
        </div>
        <button className="vp-btn vp-btn--sm" onClick={enregistrerSous} disabled={occupe === 'bibliotheque'}>
          Enregistrer sous ce nom
        </button>

        {presets.length > 0 && (
          <ul className="overlay-presets">
            {presets.map((p) => (
              <li key={p.slug}>
                <span className="overlay-preset-nom">
                  <strong>{p.name}</strong>
                  <small>{p.category}{p.has_image ? ' · avec image' : ''}</small>
                </span>
                <button className="vp-btn vp-btn--sm" onClick={() => appliquerPreset(p.slug, p.name)}
                  disabled={occupe === 'bibliotheque'}>Charger</button>
                <button className="vp-btn vp-btn--sm vp-btn--danger" onClick={() => supprimerPreset(p.slug)}
                  disabled={occupe === 'bibliotheque'}>Supprimer</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
