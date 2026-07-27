import React, { useCallback, useEffect, useState } from 'react'
import { BACKEND_BASE } from '../env.js'
import { useStore } from '../store.js'

/**
 * Ajout d'une traduction fournie par l'église.
 *
 * VersePro ne distribue que le domaine public. Une église qui possède les
 * droits d'une autre traduction l'ajoute ici : le fichier reste sur son poste.
 * Le message le rappelle, comme CONDITIONS.md.
 */
export default function BibleImport() {
  const { addToast, fetchBibles } = useStore()
  const [versions, setVersions] = useState([])
  const [sigle, setSigle] = useState('')
  const [occupe, setOccupe] = useState(false)
  const [aRedemarrer, setARedemarrer] = useState(false)

  const charger = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/imported`)
      setVersions((await r.json()).versions || [])
    } catch { /* la section reste vide, le reste des réglages fonctionne */ }
  }, [])

  useEffect(() => { charger() }, [charger])

  const importer = async (fichier) => {
    if (!fichier) return
    setOccupe(true)
    try {
      const contenu = await fichier.text()
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: contenu, version_id: sigle.trim().toUpperCase() })
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      addToast({
        message: `« ${d.id} » importée : ${d.books} livres, ${d.verses} versets`,
        kind: 'success', duration: 6000
      })
      setSigle('')
      setARedemarrer(true)
      charger()
      fetchBibles()
    } catch (err) {
      // Le message vient de la validation du serveur : il dit CE qui cloche
      // (« Genèse n'a aucun chapitre »), pas un « fichier invalide » inutile.
      addToast({ message: `Import refusé : ${err.message}`, kind: 'error', duration: 9000 })
    } finally { setOccupe(false) }
  }

  const supprimer = async (id) => {
    setOccupe(true)
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/imported/${id}`, { method: 'DELETE' })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      setVersions(d.versions || [])
      setARedemarrer(true)
    } catch (err) {
      addToast({ message: `Suppression impossible : ${err.message}`, kind: 'error' })
    } finally { setOccupe(false) }
  }

  return (
    <label>
      <small>Ajouter une traduction</small>
      <div className="bible-import-ligne">
        <input
          value={sigle}
          placeholder="Sigle (ex. SEM)"
          maxLength={8}
          onChange={(e) => setSigle(e.target.value.toUpperCase())}
        />
        <label className="vp-btn vp-btn--sm">
          {occupe ? 'Import…' : 'Fichier JSON'}
          <input type="file" accept="application/json,.json" hidden disabled={occupe}
            onChange={(e) => { importer(e.target.files?.[0]); e.target.value = '' }} />
        </label>
      </div>
      <span className="settings-muted-note">
        Format attendu : celui du corpus VersePro — <span className="mono">{'{version, language, books:[{name, abbreviation, chapters:[{chapter, verses:[{verse, text}]}]}]}'}</span>.
        Le fichier reste sur ce poste ; les droits de la traduction ajoutée relèvent de votre église.
      </span>

      {versions.length > 0 && (
        <ul className="overlay-presets">
          {versions.map((v) => (
            <li key={v.id}>
              <span className="overlay-preset-nom">
                <strong>{v.id}</strong>
                <small>{v.books} livres · {v.verses?.toLocaleString('fr-FR')} versets · {Math.round(v.bytes / 1024 / 1024 * 10) / 10} Mo</small>
              </span>
              <button type="button" className="vp-btn vp-btn--sm vp-btn--danger"
                onClick={() => supprimer(v.id)} disabled={occupe}>Retirer</button>
            </li>
          ))}
        </ul>
      )}

      {aRedemarrer && (
        <span className="settings-error-note">
          Redémarrez VersePro pour que ce changement prenne effet : le corpus et ses
          index sont chargés une seule fois, au démarrage.
        </span>
      )}
    </label>
  )
}
