import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { BACKEND_BASE } from '../env.js'
import { useStore } from '../store.js'

/**
 * Catalogue des traductions.
 *
 * Il remplace un champ « Ajouter une traduction » isolé, qui ne disait rien de
 * ce qui était déjà là. La console proposait six pastilles de version alors que
 * l'application installée n'en embarque que deux : sur le poste de
 * développement les six fichiers existent, donc tout paraissait fonctionner ;
 * chez l'église, le pasteur demandait la Semeur et le clic ne faisait rien.
 *
 * Ce tableau dit la vérité. Il classe en trois familles — livrées, domaine
 * public, sous droits — parce que ce qui décide de la présence d'une
 * traduction, ce n'est pas le goût de l'église : c'est sa licence.
 *
 * VersePro ne distribue que le domaine public. Une traduction sous droits reste
 * à la charge de qui l'ajoute (voir CONDITIONS.md).
 */

const FAMILLES = [
  {
    cle: 'livree',
    titre: 'Livrées avec VersePro',
    note: 'Domaine public. Présentes dès l’installation, rien à faire.'
  },
  {
    cle: 'publique',
    titre: 'Domaine public',
    note: 'Libres de droits, non embarquées : sept Mo chacune, pour des traductions peu employées au culte. Ajoutez le fichier si votre église les utilise.'
  },
  {
    cle: 'tierce',
    titre: 'Sous droits',
    note: 'VersePro ne les fournit pas et ne les rediffuse pas. Si votre église en possède l’usage, ajoutez son fichier : il reste sur ce poste.'
  }
]

const DEFAULT_CATALOGUE = {
  versions: [
    { id: 'LSG', nom: 'Louis Segond', annee: 1910, licence: 'domaine-public', origine: 'livree', installee: true },
    { id: 'KJF', nom: 'King James Française', annee: 2006, licence: 'domaine-public', origine: 'livree', installee: true },
    { id: 'DBY', nom: 'Darby', annee: 1885, licence: 'domaine-public', origine: 'publique', download_url: 'https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreJND.json' },
    { id: 'OST', nom: 'Ostervald', annee: 1867, licence: 'domaine-public', origine: 'publique', download_url: 'https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreBBB.json' },
    { id: 'MAR', nom: 'Martin', annee: 1744, licence: 'domaine-public', origine: 'publique', download_url: 'https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreBDM1744.json' },
    { id: 'CRA', nom: 'Crampon', annee: 1904, licence: 'domaine-public', origine: 'publique', download_url: 'https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreCrampon.json' },
    { id: 'SEM', nom: 'Bible du Semeur', annee: 2015, licence: 'sous-droits', editeur: 'Biblica', origine: 'tierce' },
    { id: 'NBS', nom: 'Nouvelle Bible Segond', annee: 2002, licence: 'sous-droits', editeur: 'Société biblique française', origine: 'tierce' },
    { id: 'TOB', nom: 'Traduction œcuménique', annee: 2010, licence: 'sous-droits', editeur: 'Cerf / SBF', origine: 'tierce' },
    { id: 'FC', nom: 'Français courant', annee: 1997, licence: 'sous-droits', editeur: 'Société biblique française', origine: 'tierce' },
    { id: 'S21', nom: 'Segond 21', annee: 2007, licence: 'sous-droits', editeur: 'Société biblique de Genève', origine: 'tierce' },
    { id: 'PDV', nom: 'Parole de Vie', annee: 2000, licence: 'sous-droits', editeur: 'Société biblique française', origine: 'tierce' }
  ],
  dossier: ''
}

export default function BibleImport() {
  const addToast = useStore(s => s.addToast)
  const fetchBibles = useStore(s => s.fetchBibles)
  const [catalogue, setCatalogue] = useState(DEFAULT_CATALOGUE)
  const [sigle, setSigle] = useState('')
  const [occupe, setOccupe] = useState(false)
  const [aRedemarrer, setARedemarrer] = useState(false)
  const [filtre, setFiltre] = useState('')

  const charger = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/catalogue`)
      if (r.ok) {
        const data = await r.json()
        if (data && Array.isArray(data.versions) && data.versions.length > 0) {
          setCatalogue(data)
        }
      }
    } catch { /* le catalogue par défaut reste affiché */ }
  }, [])

  useEffect(() => { charger() }, [charger])

  const importer = async (fichier, sigleCible) => {
    if (!fichier) return
    setOccupe(true)
    try {
      const contenu = await fichier.text()
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: contenu, version_id: (sigleCible || sigle).trim().toUpperCase() })
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      addToast({
        message: `« ${d.id} » ajoutée : ${d.books} livres, ${d.verses?.toLocaleString('fr-FR')} versets`,
        kind: 'success', duration: 6000
      })
      setSigle('')
      setARedemarrer(true)
      charger()
      fetchBibles()
    } catch (err) {
      // Le message vient de la validation du serveur : il dit CE qui cloche
      // (« Genèse n'a aucun chapitre »), pas un « fichier invalide » inutile.
      addToast({ message: `Ajout refusé : ${err.message}`, kind: 'error', duration: 9000 })
    } finally { setOccupe(false) }
  }

  const telechargerEtInstaller = async (versionId) => {
    setOccupe(true)
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/download_public/${versionId}`, {
        method: 'POST'
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      addToast({
        message: `« ${d.id} » téléchargée et installée ! (${d.verses?.toLocaleString('fr-FR')} versets)`,
        kind: 'success', duration: 6000
      })
      setARedemarrer(true)
      charger()
      fetchBibles()
    } catch (err) {
      addToast({ message: `Échec du téléchargement : ${err.message}`, kind: 'error', duration: 9000 })
    } finally { setOccupe(false) }
  }

  const supprimer = async (id) => {
    setOccupe(true)
    try {
      const r = await fetch(`${BACKEND_BASE}/api/v1/bibles/imported/${id}`, { method: 'DELETE' })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`)
      setARedemarrer(true)
      charger()
      fetchBibles()
    } catch (err) {
      addToast({ message: `Retrait impossible : ${err.message}`, kind: 'error' })
    } finally { setOccupe(false) }
  }

  const versions = catalogue.versions || []
  const nbInstallees = versions.filter((v) => v.installee).length

  const parFamille = useMemo(() => {
    const terme = filtre.trim().toLowerCase()
    const retenues = terme
      ? versions.filter((v) =>
          v.id.toLowerCase().includes(terme) || (v.nom || '').toLowerCase().includes(terme))
      : versions
    return FAMILLES.map((f) => ({
      ...f,
      entrees: retenues.filter((v) => v.origine === f.cle)
    })).filter((f) => f.entrees.length > 0)
  }, [versions, filtre])

  return (
    <div className="bible-catalogue">
      <div className="bible-catalogue-head">
        <div>
          <strong>{nbInstallees} traduction{nbInstallees > 1 ? 's' : ''} utilisable{nbInstallees > 1 ? 's' : ''}</strong>
          <small>Seules celles-ci apparaissent dans les pastilles de version, en direct.</small>
        </div>
        <input
          className="vp-input bible-catalogue-filtre"
          value={filtre}
          placeholder="Filtrer…"
          onChange={(e) => setFiltre(e.target.value)}
        />
      </div>

      {parFamille.map((famille) => (
        <section key={famille.cle} className="bible-catalogue-famille">
          <span className="vp-label">{famille.titre}</span>
          <p className="settings-muted-note">{famille.note}</p>

          <ul className="bible-catalogue-liste">
            {famille.entrees.map((v) => (
              <li key={v.id} className={v.installee ? 'is-installee' : ''}>
                <span className="bible-catalogue-sigle">{v.id}</span>
                <span className="bible-catalogue-nom">
                  <strong>{v.nom}</strong>
                  <small>
                    {v.annee ? `${v.annee}` : 'année inconnue'}
                    {v.editeur ? ` · ${v.editeur}` : ''}
                    {v.versets ? ` · ${v.versets.toLocaleString('fr-FR')} versets` : ''}
                  </small>
                </span>

                {v.installee ? (
                  <span className="bible-catalogue-etat is-ok">Installée</span>
                ) : (
                  <span className="bible-catalogue-etat">Absente</span>
                )}

                {/* Une version livrée ne se retire pas : la détection s'appuie
                    sur le corpus de référence. */}
                {v.amovible ? (
                  <button type="button" className="vp-btn vp-btn--sm vp-btn--danger"
                    onClick={() => supprimer(v.id)} disabled={occupe}>Retirer</button>
                ) : v.origine === 'livree' ? (
                  <span className="bible-catalogue-verrou" title="Livrée avec VersePro">—</span>
                ) : (
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {v.download_url && (
                      <>
                        <button
                          type="button"
                          className="vp-btn vp-btn--sm vp-btn--primary"
                          onClick={() => telechargerEtInstaller(v.id)}
                          disabled={occupe}
                          style={{
                            background: 'var(--vp-accent, #0ea5e9)',
                            color: '#fff',
                            fontWeight: 600,
                            padding: '6px 12px'
                          }}
                        >
                          {occupe ? '…' : '📥 Installer (1-Clic)'}
                        </button>
                        <a
                          href={v.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="vp-btn vp-btn--sm vp-btn--ghost"
                          title="Lien direct pour télécharger le fichier JSON"
                          style={{ textDecoration: 'none', padding: '6px 10px', fontSize: '11px' }}
                        >
                          🔗 Lien JSON
                        </a>
                      </>
                    )}
                    <label className="vp-btn vp-btn--sm vp-btn--ghost" aria-disabled={occupe} style={{ padding: '6px 10px', fontSize: '11px' }}>
                      {occupe ? '…' : '📁 Fichier local'}
                      <input type="file" accept="application/json,.json" hidden disabled={occupe}
                        onChange={(e) => { importer(e.target.files?.[0], v.id); e.target.value = '' }} />
                    </label>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      {/* Une église peut employer une traduction absente du catalogue. */}
      <section className="bible-catalogue-famille">
        <span className="vp-label">Autre traduction</span>
        <div className="bible-import-ligne">
          <input
            className="vp-input"
            value={sigle}
            placeholder="Sigle (ex. NEG79)"
            maxLength={8}
            onChange={(e) => setSigle(e.target.value.toUpperCase())}
          />
          <label className="vp-btn vp-btn--sm">
            {occupe ? 'Ajout…' : 'Fichier JSON'}
            <input type="file" accept="application/json,.json" hidden disabled={occupe || !sigle.trim()}
              onChange={(e) => { importer(e.target.files?.[0]); e.target.value = '' }} />
          </label>
        </div>
        <span className="settings-muted-note">
          Format attendu : celui du corpus VersePro — <span className="mono">{'{version, language, books:[{name, abbreviation, chapters:[{chapter, verses:[{verse, text}]}]}]}'}</span>.
        </span>
      </section>

      {catalogue.dossier && (
        <span className="settings-muted-note bible-catalogue-dossier">
          Dossier des traductions sur ce poste :<br />
          <span className="mono">{catalogue.dossier}</span>
        </span>
      )}

      {aRedemarrer && (
        <span className="settings-error-note">
          Redémarrez VersePro pour que ce changement prenne effet : le corpus et ses
          index sont chargés une seule fois, au démarrage.
        </span>
      )}
    </div>
  )
}
