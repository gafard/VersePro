import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { BACKEND_BASE } from '../env.js'
import OverlayEditor from './OverlayEditor.jsx'
import BibleImport from './BibleImport.jsx'

// Regroupement des réglages. L'ordre suit celui d'une mise en route : on
// branche le micro, on choisit les moteurs, on règle ce qui s'affiche, on
// connecte les sorties, et le reste ne sert qu'occasionnellement.
const ONGLETS = [
  { cle: 'audio', nom: 'Audio', note: 'micro, filtres' },
  { cle: 'moteurs', nom: 'Moteurs', note: 'transcription, IA' },
  { cle: 'projection', nom: 'Projection', note: 'thèmes, habillage' },
  { cle: 'sorties', nom: 'Sorties', note: 'ProPresenter, NDI' },
  { cle: 'avance', nom: 'Avancé', note: 'répétition, version' }
]

/**
 * Aperçu d'un style de projection : la page /output elle-même, rendue en
 * 1280×720 puis réduite. On ne laisse pas l'iframe s'adapter d'elle-même —
 * les styles historiques sont dimensionnés en rem (base fixe de 16 px) et
 * paraîtraient énormes dans une petite boîte ; à l'échelle, ils s'affichent
 * comme sur le vidéoprojecteur.
 */
function StylePreview({ theme = 'broadcast', style = 'default' }) {
  const boite = useRef(null)
  const [echelle, setEchelle] = useState(0.25)
  useEffect(() => {
    const el = boite.current
    if (!el) return
    const mesurer = () => setEchelle(el.clientWidth / 1280)
    mesurer()
    const observateur = new ResizeObserver(mesurer)
    observateur.observe(el)
    return () => observateur.disconnect()
  }, [])
  // `demo` demande à la page d'afficher un verset d'exemple si rien n'est
  // projeté : sans lui, l'aperçu reste noir tant que le culte n'a pas commencé.
  const url = `${BACKEND_BASE}/output?theme=${theme}&style=${style}&demo=1`
  return (
    <div className="style-preview" ref={boite}>
      <iframe
        key={url}
        title={`Aperçu du thème ${theme}`}
        src={url}
        style={{ transform: `scale(${echelle})` }}
        loading="lazy"
      />
    </div>
  )
}

const BIBLE_NAMES = {
  LSG: 'Louis Segond 1910',
  SEM: 'La Bible du Semeur',
  KJF: 'King James Française',
  NBS: 'Nouvelle Bible Segond',
  FC: 'Français Courant',
  TOB: 'Traduction Oecumenique'
}

export default function Settings() {
  const {
    settings,
    fetchSettings,
    updateSettings,
    availableBibles,
    fetchBibles,
    activeBible,
    aiActive,
    propresenterConnected,
    addToast,
    asrStatus,
    semanticStatus,
    fetchIntelligenceStatus,
    prepareSemanticIndex,
    prepareWhisper,
    connected,
    connectionStatus,
    audioDevices,
    selectedAudioDeviceId,
    setSelectedAudioDeviceId,
    refreshAudioDevices,
    audioFilterMode,
    setAudioFilterMode
  } = useStore()

  const [form, setForm] = useState({
    auto_send: false,
    sunday_safe_mode: true,
    shadow_mode: false,
    bible_version: activeBible || 'LSG',
    propresenter_host: '127.0.0.1',
    propresenter_port: 1025,
    propresenter_message_name: 'VersePro',
    ndi_enabled: false,
    ndi_source_name: 'VersePro',
    deepgram_model: 'nova-2',
    deepgram_language: 'fr',
    ai_agent_enabled: true,
    ai_confidence_threshold: 95,
    ai_filtering_mode: 'strict',
    voice_gate_enabled: false,
    asr_default_engine: 'auto',
    local_semantic_enabled: true,
    local_semantic_threshold: 0.865,
    projection_theme: 'presentation',
    projection_style: 'default',
    show_bible_version: true,
    dual_translations: 'LSG,KJF'
  })
  const [secretForm, setSecretForm] = useState({
    deepgram_api_key: '',
    openrouter_api_key: '',
    gemini_api_key: ''
  })
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)
  const [helpModal, setHelpModal] = useState(null)

  // Version installée et, si un manifeste est configuré, disponibilité d'une
  // mise à jour. L'appel échoue en silence : hors ligne, la section affiche
  // simplement la version installée.
  const [versionInfo, setVersionInfo] = useState(null)
  useEffect(() => {
    let vivant = true
    fetch(`${BACKEND_BASE}/api/v1/update/check`)
      .then((r) => r.json())
      .then((d) => { if (vivant) setVersionInfo(d) })
      .catch(() => {})
    return () => { vivant = false }
  }, [])
  const [rehearseText, setRehearseText] = useState('')
  const [rehearseResults, setRehearseResults] = useState(null)
  const [rehearsing, setRehearsing] = useState(false)
  const [preparingLocal, setPreparingLocal] = useState('')
  // Onglets de la console : onze cartes d'affilée obligeaient à faire défiler
  // longtemps pour trouver un réglage. L'onglet est mémorisé — un bénévole qui
  // revient tombe là où il s'était arrêté.
  const [onglet, setOnglet] = useState(() => {
    try { return localStorage.getItem('versepro_settings_tab') || 'audio' } catch { return 'audio' }
  })
  const changerOnglet = (cle) => {
    setOnglet(cle)
    try { localStorage.setItem('versepro_settings_tab', cle) } catch { /* stockage privé */ }
  }
  // Habillages enregistrés : ils s'ajoutent au menu des styles, dans leur
  // catégorie. Rechargés à chaque passage sur l'onglet Projection pour refléter
  // un enregistrement fait juste en dessous, dans l'éditeur.
  const [presetsHabillage, setPresetsHabillage] = useState([])
  useEffect(() => {
    if (onglet !== 'projection') return
    let vivant = true
    fetch(`${BACKEND_BASE}/api/v1/overlay/library`)
      .then((r) => r.json())
      .then((d) => { if (vivant) setPresetsHabillage(d.presets || []) })
      .catch(() => {})
    return () => { vivant = false }
  }, [onglet, savedAt])
  const updateAudioDevice = (deviceId) => {
    setSelectedAudioDeviceId(deviceId)
    addToast({ message: 'Entrée micro mise à jour', kind: 'success' })
  }

  const runRehearsal = async () => {
    if (!rehearseText.trim()) return
    setRehearsing(true)
    setRehearseResults(null)
    try {
      const response = await fetch(`${BACKEND_BASE}/api/v1/rehearse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: rehearseText })
      })
      const data = await response.json()
      setRehearseResults(data.detections || [])
    } catch {
      setRehearseResults([])
    } finally {
      setRehearsing(false)
    }
  }

  useEffect(() => {
    fetchBibles()
    fetchSettings()
    fetchIntelligenceStatus()
    refreshAudioDevices()
    navigator.mediaDevices?.addEventListener?.('devicechange', refreshAudioDevices)
    const statusTimer = setInterval(fetchIntelligenceStatus, 5000)
    return () => {
      navigator.mediaDevices?.removeEventListener?.('devicechange', refreshAudioDevices)
      clearInterval(statusTimer)
    }
  }, [])

  useEffect(() => {
    if (!settings) return
    setForm({
      auto_send: Boolean(settings.auto_send),
      sunday_safe_mode: settings.sunday_safe_mode !== false,
      shadow_mode: Boolean(settings.shadow_mode),
      bible_version: settings.bible_version || activeBible || 'LSG',
      propresenter_host: settings.propresenter_host || '127.0.0.1',
      propresenter_port: settings.propresenter_port || 1025,
      propresenter_message_name: settings.propresenter_message_name || 'VersePro',
      ndi_enabled: Boolean(settings.ndi?.enabled),
      ndi_source_name: settings.ndi?.source_name || 'VersePro',
      deepgram_model: settings.deepgram_model || 'nova-2',
      deepgram_language: settings.deepgram_language || 'fr',
      ai_agent_enabled: Boolean(settings.ai_agent_enabled),
      ai_confidence_threshold: settings.ai_confidence_threshold || 95,
      ai_filtering_mode: settings.ai_filtering_mode || 'strict',
      voice_gate_enabled: Boolean(settings.voice_gate_enabled),
      asr_default_engine: settings.asr_default_engine || 'auto',
      local_semantic_enabled: settings.local_semantic_enabled !== false,
      local_semantic_threshold: Number(settings.local_semantic_threshold || 0.865),
      projection_theme: settings.projection_theme || 'presentation',
      projection_style: settings.projection_style || 'default',
      show_bible_version: settings.show_bible_version !== false,
      dual_translations: settings.dual_translations || 'LSG,KJF'
    })
  }, [settings, activeBible])

  const statusCards = useMemo(() => ([
    {
      label: 'Serveur',
      // Même nuance que l'en-tête : au premier lancement le moteur charge ses
      // index pendant plusieurs secondes — « Hors ligne » faisait croire à une panne.
      value: connected ? 'Connecté' : connectionStatus === 'starting' ? 'Démarrage' : 'Hors ligne',
      tone: connected ? 'good' : 'warn'
    },
    {
      label: 'ProPresenter',
      value: propresenterConnected ? 'Prêt' : 'Manuel',
      tone: propresenterConnected ? 'good' : 'warn'
    },
    {
      label: 'IA',
      value: aiActive ? 'Active' : 'Inactive',
      tone: aiActive ? 'good' : 'neutral'
    }
  ]), [connected, connectionStatus, propresenterConnected, aiActive])

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const updateSecret = (field, value) => {
    setSecretForm((current) => ({ ...current, [field]: value }))
  }

  const handleDualBibleToggle = (code) => {
    let current = form.dual_translations ? form.dual_translations.split(',').map(s => s.trim()) : []
    if (current.includes(code)) {
      current = current.filter(c => c !== code)
    } else {
      current.push(code)
    }
    if (current.length === 0) current = ['LSG']
    updateField('dual_translations', current.join(','))
  }

  const save = async () => {
    setSaving(true)
    try {
      const secrets = Object.fromEntries(
        Object.entries(secretForm)
          .map(([key, value]) => [key, String(value || '').trim()])
          .filter(([, value]) => value.length > 0)
      )
      const payload = {
        ...form,
        ...secrets,
        propresenter_port: Number(form.propresenter_port) || 1025,
        ai_confidence_threshold: Math.min(99, Math.max(50, Number(form.ai_confidence_threshold) || 95))
      }
      const result = await updateSettings(payload)
      if (result) {
        setSavedAt(new Date())
        addToast({ message: 'Paramètres sauvegardés', kind: 'success' })
        setSecretForm({
          deepgram_api_key: '',
          openrouter_api_key: '',
          gemini_api_key: ''
        })
      }
    } finally {
      setSaving(false)
    }
  }

  const prepareLocalEngine = async (kind) => {
    setPreparingLocal(kind)
    try {
      if (kind === 'whisper') {
        await prepareWhisper('auto')
        addToast({ message: 'Préparation de Whisper lancée', kind: 'success' })
      } else {
        await prepareSemanticIndex()
        addToast({ message: 'Indexation sémantique lancée', kind: 'success' })
      }
    } catch (error) {
      // Le message générique masquait la vraie cause (souvent : pas d'Internet
      // pour ce premier téléchargement, ou serveur local injoignable). On la dit.
      const isNetwork = error?.name === 'TypeError' || /fetch/i.test(error?.message || '')
      const reason = isNetwork ? 'serveur local injoignable' : (error?.message || 'raison inconnue')
      addToast({ message: `Préparation locale impossible : ${reason}`, kind: 'error', duration: 7000 })
    } finally {
      setPreparingLocal('')
    }
  }

  return (
    <div className="settings-page app-soft-page">
      <section className="settings-hero">
        <div>
          <span>Paramètres</span>
          <h1>Console de configuration</h1>
          <p>
            Les réglages critiques restent lisibles, calmes et modifiables sans toucher aux fichiers système.
          </p>
        </div>

        <div className="settings-status-grid">
          {statusCards.map((card) => (
            <div key={card.label} className={`settings-status-card is-${card.tone}`}>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <nav className="settings-tabs" aria-label="Catégories de réglages">
        {ONGLETS.map(({ cle, nom, note }) => (
          <button
            key={cle}
            type="button"
            className={`settings-tab ${onglet === cle ? 'is-active' : ''}`}
            aria-current={onglet === cle ? 'page' : undefined}
            onClick={() => changerOnglet(cle)}
          >
            <strong>{nom}</strong>
            <small>{note}</small>
          </button>
        ))}
      </nav>

      {/* Le filtre est porté par la grille : chaque carte déclare sa catégorie
          et le CSS masque les autres. Découper le JSX en dix fragments
          conditionnels aurait multiplié les risques pour le même résultat. */}
      <section className="settings-grid" data-active={onglet}>
        <div data-cat="audio" className="settings-card is-wide is-primary">
          <div className="settings-card-head">
            <div>
              <span>Audio</span>
              <h2>Entrée micro</h2>
            </div>
            <button type="button" className="vp-btn vp-btn--ghost vp-btn--sm" onClick={refreshAudioDevices}>
              Actualiser
            </button>
          </div>
          <p>
            Choisissez ici le micro ou l'interface audio de la régie. Le live garde seulement
            le démarrage, l'arrêt et le niveau du signal.
          </p>
          <label>
            <small>Source audio par défaut</small>
            <select value={selectedAudioDeviceId} onChange={(e) => updateAudioDevice(e.target.value)}>
              {audioDevices.length === 0 ? (
                <option value="">Micro par défaut du navigateur</option>
              ) : (
                audioDevices.map((device, index) => (
                  <option key={device.deviceId || index} value={device.deviceId}>
                    {device.label || `Micro ${index + 1}`}
                  </option>
                ))
              )}
            </select>
          </label>
          <label>
            <small>Prétraitement audio</small>
            <select value={audioFilterMode} onChange={(e) => setAudioFilterMode(e.target.value)}>
              <option value="off">Signal brut (recommandé)</option>
              <option value="speech">Parole: 80 Hz à 8 kHz</option>
              <option value="church">Église avec musique: 120 Hz à 7 kHz</option>
            </select>
          </label>
          <span className="settings-secret-hint">
            Le filtre Église atténue les graves continus sans couper les consonnes. Le signal brut reste le choix le plus fidèle avec une sortie console propre.
          </span>
        </div>

        <div data-cat="moteurs" className="settings-card is-wide">
          <div className="settings-card-head">
            <div>
              <span>Intelligence locale</span>
              <h2>Transcription et recherche hors ligne</h2>
            </div>
            <span className={`vp-chip ${semanticStatus?.installed ? 'is-accent' : ''}`}>
              {semanticStatus?.installed && asrStatus?.whisper?.ready
                ? 'Prêt'
                : semanticStatus?.installed
                  ? 'Recherche prête'
                  : asrStatus?.whisper?.ready
                    ? 'Voix prête'
                    : 'À préparer'}
            </span>
          </div>
          <p>
            Le mode automatique privilégie Deepgram quand Internet est disponible,
            puis bascule sur Vosk local si la connexion tombe. Whisper, plus lent
            au réel, reste un second choix explicite.
          </p>
          <div className="settings-form-grid">
            <label>
              <small>Moteur par défaut</small>
              <select value={form.asr_default_engine} onChange={(e) => updateField('asr_default_engine', e.target.value)}>
                <option value="auto">Auto (Deepgram puis local)</option>
                <option value="deepgram">Deepgram cloud</option>
                <option value="local_auto">Local auto (Vosk puis Whisper)</option>
                <option value="vosk">Vosk local (recommandé)</option>
                <option value="whisper">Whisper local (plus lent)</option>
              </select>
            </label>
          </div>
          <div className="settings-divider">
            <div className="settings-card-head">
              <div>
                <small>Whisper local adaptatif</small>
                <p>
                  {asrStatus?.whisper?.ready
                    ? `Prêt · modèle ${asrStatus.whisper.model}`
                    : asrStatus?.whisper?.preparing
                      ? 'Téléchargement ou chargement en cours'
                      : `Non préparé · modèle conseillé ${asrStatus?.whisper?.model || 'auto'}`}
                </p>
              </div>
              <span className={`vp-chip ${asrStatus?.whisper?.ready ? 'is-ok' : ''}`}>
                {asrStatus?.whisper?.ready ? 'Prêt' : 'Optionnel'}
              </span>
            </div>
            {asrStatus?.whisper?.last_error && !asrStatus?.whisper?.ready && (
              <span className="settings-error-note" role="alert">
                Échec : {asrStatus.whisper.last_error}
              </span>
            )}
            <button
              type="button"
              className="vp-btn vp-btn--sm"
              onClick={() => prepareLocalEngine('whisper')}
              disabled={preparingLocal === 'whisper' || asrStatus?.whisper?.preparing}
            >
              {asrStatus?.whisper?.ready ? 'Whisper prêt' : 'Préparer Whisper'}
            </button>
            <span className="settings-muted-note">
              Plus robuste que Vosk sur les accents et le multilingue, avec une latence par fenêtre d'environ 2,4 secondes sur CPU.
            </span>
          </div>
          <div className="settings-divider">
            <div className="settings-card-head">
              <div>
                <small>Embeddings bibliques ONNX</small>
                <p>
                  {semanticStatus?.verses_indexed || 0} versets indexés localement
                  {semanticStatus?.model ? ` · moteur ${semanticStatus.model === 'e5-base' ? 'e5-base (précis)' : semanticStatus.model === 'e5-small' ? 'e5-small (léger, repli)' : semanticStatus.model}` : ''}
                  {semanticStatus?.using_fallback ? ' · secours' : ''}
                </p>
              </div>
              <label className="settings-switch">
                <input type="checkbox" checked={form.local_semantic_enabled} onChange={(e) => updateField('local_semantic_enabled', e.target.checked)} />
                <span />
              </label>
            </div>
            <label>
              <small>Seuil sémantique : <strong>{Math.round(form.local_semantic_threshold * 100)} %</strong></small>
              <input type="range" min="0.50" max="0.95" step="0.005" value={form.local_semantic_threshold} onChange={(e) => updateField('local_semantic_threshold', Number(e.target.value))} />
              <span className="settings-muted-note">Calibré automatiquement selon le moteur actif — n'ajustez qu'en cas de faux positifs ou d'oublis répétés.</span>
            </label>
            {semanticStatus?.last_error && !semanticStatus?.installed && (
              <span className="settings-error-note" role="alert">
                Échec : {semanticStatus.last_error}
              </span>
            )}
            <button type="button" className="vp-btn vp-btn--sm" onClick={() => prepareLocalEngine('semantic')} disabled={preparingLocal === 'semantic' || semanticStatus?.indexing}>
              {semanticStatus?.installed ? 'Réindexer' : semanticStatus?.indexing ? 'Indexation…' : 'Installer et indexer'}
            </button>
            <span className="settings-muted-note">
              Première préparation uniquement : plusieurs minutes selon le processeur. Elle ne démarre jamais pendant le live sans votre action.
            </span>
          </div>
        </div>

        <div data-cat="projection" className="settings-card is-wide">
          <div className="settings-card-head">
            <div>
              <span>Projection</span>
              <h2>Diffusion en direct</h2>
            </div>
            <label className="settings-switch">
              <input
                type="checkbox"
                checked={form.auto_send}
                onChange={(e) => updateField('auto_send', e.target.checked)}
              />
              <span />
            </label>
          </div>
          <p>
            La projection automatique reste réservée aux références explicites et vérifiées.
            Les suggestions sémantiques et IA exigent toujours une validation humaine.
          </p>
          <div className="settings-form-grid">
            <label className="settings-inline-check">
              <input
                type="checkbox"
                checked={form.sunday_safe_mode}
                onChange={(e) => updateField('sunday_safe_mode', e.target.checked)}
              />
              <span><strong>Mode dimanche sûr</strong><small>Bloque toute projection automatique.</small></span>
            </label>
            <label className="settings-inline-check">
              <input
                type="checkbox"
                checked={form.shadow_mode}
                onChange={(e) => updateField('shadow_mode', e.target.checked)}
              />
              <span><strong>Mode ombre</strong><small>Analyse le culte sans piloter les sorties.</small></span>
            </label>
          </div>
        </div>

        <div data-cat="projection" className="settings-card is-wide">
          <span>Projection & Rendu</span>
          <h2>Thèmes & Personnalisation</h2>
          
          <div className="settings-form-grid" style={{ marginTop: '16px' }}>
            {/* Colonne de gauche : les menus, puis l'aperçu juste dessous. Il
                comble ainsi le vide d'origine sans repousser l'habillage, qui
                garde sa place à droite — là où l'opérateur a l'habitude de le
                chercher. */}
            <div className="settings-stack">
            <div className="settings-two-cols">
              <label>
                <small>Thème d'affichage</small>
                <select 
                  value={form.projection_theme} 
                  onChange={(e) => updateField('projection_theme', e.target.value)}
                >
                  <option value="presentation">presentation (Plein écran classique)</option>
                  <option value="broadcast">broadcast (Incrustation / Lower-third)</option>
                  <option value="confidence">confidence (Moniteur retour scène)</option>
                  <option value="elegant">elegant (Cérémonie, Serif Doré)</option>
                  <option value="minimal">minimal (Typographie géante épurée)</option>
                  <option value="dual">dual (Comparatif multi-versions)</option>
                  <option value="poster">poster (Cadre vertical)</option>
                  <option value="souffle">souffle (Adoration — texte seul, aucun décor)</option>
                  <option value="story">story (Format vertical avec fond)</option>
                </select>
              </label>

              {form.projection_theme === 'broadcast' ? (
                <label>
                  <small>Style de Lower-Third</small>
                  <select 
                    value={form.projection_style} 
                    onChange={(e) => updateField('projection_style', e.target.value)}
                  >
                    <option value="agoe-logope">🔥 agoe-logope (Exact Trait pour Trait — Panneau blanc, étiquette émeraude & exposant)</option>
                    <option value="bandeau">bandeau (Panneau blanc, étiquette turquoise)</option>
                    <option value="filet">filet (Recommandé — règle laiton, sans cadre)</option>
                    <option value="default">default (Classique translucide)</option>
                    <option value="glass">✨ glass (Aero Dépoli Acrylique)</option>
                    <option value="neon-glow">✨ neon-glow (Cyberpunk épuré)</option>
                    <option value="elegant-serif">✨ elegant-serif (Georgia & Or)</option>
                    <option value="pill">pill (Capsule arrondie)</option>
                    <option value="sage">sage (Sauge & Terracotta)</option>
                    <option value="split">split (Barre complète divisée)</option>
                    {/* Habillages de l'église, rangés par catégorie, à côté des
                        styles livrés : un habillage créé devient un choix comme
                        un autre. */}
                    {Object.entries(
                      presetsHabillage.reduce((groupes, p) => {
                        (groupes[p.category] ||= []).push(p)
                        return groupes
                      }, {})
                    ).map(([categorie, liste]) => (
                      <optgroup key={categorie} label={categorie}>
                        {liste.map((p) => (
                          <option key={p.slug} value={`habillage:${p.slug}`}>
                            {p.name}{p.has_image ? ' (avec image)' : ''}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
              ) : (
                <div style={{ opacity: 0.4, pointerEvents: 'none' }}>
                  <label>
                    <small>Style de Lower-Third</small>
                    <select disabled value="default">
                      <option value="default">Indisponible avec ce thème</option>
                    </select>
                  </label>
                </div>
              )}
            </div>

            {/* Aperçu RÉEL : la page de projection elle-même, sur le thème ET
                le style choisis. Une vignette dessinée à la main aurait fini
                par mentir dès qu'un style change ; ici c'est le vrai rendu. */}
            <div className="settings-divider">
              <div className="settings-card-head">
                <div>
                  <small>Aperçu</small>
                  <p>Le rendu exact, thème et style combinés, tel qu'il sortira sur l'écran.</p>
                </div>
                <span className="vp-chip">
                  {form.projection_theme}{form.projection_theme === 'broadcast' ? ` · ${form.projection_style}` : ''}
                </span>
              </div>
              <StylePreview theme={form.projection_theme} style={form.projection_style} />
            </div>
            </div>

            <div className="settings-divider">
              <div className="settings-card-head">
                <div>
                  <small>Habillage de l'église</small>
                  <p>
                    Importez votre propre graphique (PNG à fond transparent, exporté de Canva,
                    Photoshop…) : VersePro n'y pose que le verset et sa référence. Le rendu n'est
                    pas une imitation de votre design — c'est votre fichier. Un habillage installé
                    remplace le style choisi ci-dessus.
                  </p>
                </div>
              </div>
              <OverlayEditor />
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={form.show_bible_version}
                  onChange={(e) => updateField('show_bible_version', e.target.checked)}
                  style={{ width: '16px', height: '16px' }}
                />
                <span className="text-xs text-[var(--text)]">
                  Indiquer l'édition sous le verset. Les styles <strong>filet</strong>, <strong>cartouche</strong>,
                  <strong> ligne</strong> et le thème <strong>souffle</strong> l'écrivent en toutes lettres
                  (<strong>Louis Segond 1910</strong>) ; les autres gardent le sigle (<strong>Jean 3:16 (LSG)</strong>).
                </span>
              </label>
            </div>

            {form.projection_theme === 'dual' && (
              <div className="flex flex-col gap-2 pt-3 border-t border-border-weak">
                <small className="block font-semibold mb-1 text-[var(--text-dim)]">Traductions à projeter en parallèle (Duo / Trio) :</small>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {availableBibles.map((code) => {
                    const isChecked = form.dual_translations?.split(',').map(s => s.trim()).includes(code);
                    return (
                      <label key={code} className="flex items-center gap-2 cursor-pointer text-xs select-none">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleDualBibleToggle(code)}
                          style={{ width: '14px', height: '14px' }}
                        />
                        <span>{code} ({BIBLE_NAMES[code] || code})</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="pt-3 border-t border-border-weak">
              <small className="block font-semibold mb-1 text-[var(--text-dim)]">Lien d'intégration OBS / vMix :</small>
              <div className="flex gap-2 items-center bg-[var(--color-paper-deep)] border border-border-weak rounded-lg p-2 font-mono text-[10px] text-accent truncate select-all">
                <span>
                  {`${BACKEND_BASE || 'http://127.0.0.1:8001'}/output?theme=${form.projection_theme}&style=${form.projection_style}&versions=${form.dual_translations}&subtitle=off`}
                </span>
                <button
                  type="button"
                  className="vp-btn vp-btn--ghost vp-btn--2xs ml-auto flex-shrink-0"
                  onClick={() => {
                    const url = `${BACKEND_BASE || 'http://127.0.0.1:8001'}/output?theme=${form.projection_theme}&style=${form.projection_style}&versions=${form.dual_translations}&subtitle=off`;
                    navigator.clipboard.writeText(url);
                    addToast({ message: 'URL copiée !', kind: 'success' });
                  }}
                >
                  Copier
                </button>
              </div>
              <span className="settings-muted-note mt-1 block">
                Ajoutez ce lien comme source navigateur (Browser Source) dans OBS Studio ou vMix (1920x1080, fond transparent).
              </span>
            </div>
          </div>
        </div>

        <div data-cat="projection" className="settings-card">
          <span>Bible</span>
          <h2>Version par défaut</h2>
          <div className="settings-two-cols">
            <label>
              <small>Version projetée</small>
              <select value={form.bible_version} onChange={(e) => updateField('bible_version', e.target.value)}>
                {availableBibles.map((code) => (
                  <option key={code} value={code}>
                    {code} - {BIBLE_NAMES[code] || code}
                  </option>
                ))}
              </select>
            </label>
            {/* Import à droite du sélecteur, là où on cherche naturellement à
                compléter la liste. */}
            <BibleImport />
          </div>
        </div>

        <div data-cat="sorties" className="settings-card">
          <div className="settings-card-head">
            <div>
              <span>NDI</span>
              <h2>Diffusion vers le mélangeur</h2>
            </div>
            <span className={`vp-chip ${settings?.ndi?.sending ? 'is-ok' : settings?.ndi?.available ? '' : 'is-warn'}`}>
              {settings?.ndi?.sending ? 'À l\'antenne' : settings?.ndi?.available ? 'Prêt' : 'Indisponible'}
            </span>
          </div>
          <p>
            Envoie le bandeau — habillage compris, fond transparent — sur le réseau
            local. La source apparaît dans vMix, OBS ou TriCaster sans câble ni
            capture d'écran. L'image diffusée est identique à celle de l'écran.
          </p>
          {settings?.ndi?.available ? (
            <>
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={form.ndi_enabled}
                  onChange={(e) => updateField('ndi_enabled', e.target.checked)}
                />
                <span><strong>Activer la sortie NDI</strong></span>
              </label>
              <label>
                <small>Nom de la source</small>
                <input
                  value={form.ndi_source_name}
                  onChange={(e) => updateField('ndi_source_name', e.target.value)}
                />
                <span className="settings-muted-note">
                  Nom affiché dans la liste des sources du mélangeur.
                </span>
              </label>
            </>
          ) : (
            <span className="settings-error-note">
              NDI n'est pas disponible sur ce poste{settings?.ndi?.last_error ? ` : ${settings.ndi.last_error}` : ''}.
              Installez le runtime NDI de Vizrt, puis relancez VersePro.
            </span>
          )}
        </div>

        <div data-cat="sorties" className="settings-card">
          <span>ProPresenter</span>
          <h2>Connexion locale</h2>
          <div className="settings-two-cols">
            <label>
              <small>Hôte</small>
              <input
                value={form.propresenter_host}
                onChange={(e) => updateField('propresenter_host', e.target.value)}
              />
            </label>
            <label>
              <small>Port</small>
              <input
                type="number"
                value={form.propresenter_port}
                onChange={(e) => updateField('propresenter_port', e.target.value)}
              />
            </label>
          </div>
          <label>
            <small>Nom du message ProPresenter</small>
            <input
              value={form.propresenter_message_name}
              onChange={(e) => updateField('propresenter_message_name', e.target.value)}
            />
            <span className="settings-muted-note">
              Vos habillages restent les vôtres : créez dans ProPresenter un Message
              portant ce nom, stylé comme votre église le souhaite, avec un jeton de
              référence et un jeton de texte. VersePro ne fait que les remplir.
            </span>
          </label>
        </div>

        <div data-cat="moteurs" className="settings-card">
          <span>Deepgram</span>
          <h2>Transcription cloud</h2>
          <div className="settings-two-cols">
            <label>
              <small>Modèle</small>
              <select value={form.deepgram_model} onChange={(e) => updateField('deepgram_model', e.target.value)}>
                <option value="nova-2">nova-2</option>
                <option value="nova-3">nova-3</option>
                <option value="base">base</option>
                <option value="enhanced">enhanced</option>
              </select>
            </label>
            <label>
              <small>Langue</small>
              <select value={form.deepgram_language} onChange={(e) => updateField('deepgram_language', e.target.value)}>
                <option value="fr">Français</option>
                <option value="en">Anglais</option>
                <option value="es">Espagnol</option>
                <option value="pt">Portugais</option>
              </select>
            </label>
          </div>
          <div className="settings-divider">
            <label>
              <small className="settings-label-row">
                <span>Clé API Deepgram</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('deepgram')}
                  className="settings-help-button"
                >
                  Obtenir une clé
                </button>
              </small>
              <input
                type="password"
                placeholder={settings?.deepgram_api_key_configured ? `Configuree (${settings.deepgram_api_key_hint})` : 'Coller une cle Deepgram'}
                value={secretForm.deepgram_api_key}
                onChange={(e) => updateSecret('deepgram_api_key', e.target.value)}
              />
            </label>
            <span className="settings-secret-hint">
              Le backend conserve la cle. L interface ne la relit jamais en clair.
            </span>
          </div>
        </div>

        <div data-cat="moteurs" className="settings-card is-wide">
          <div className="settings-card-head">
            <div>
              <span>Analyse intelligente</span>
              <h2>Moteur semantique</h2>
            </div>
            <label className="settings-switch">
              <input
                type="checkbox"
                checked={form.ai_agent_enabled}
                onChange={(e) => updateField('ai_agent_enabled', e.target.checked)}
              />
              <span />
            </label>
          </div>
          <p>
            L'IA peut proposer une référence quand le prédicateur paraphrase, mais elle ne doit pas prendre le contrôle de l'écran.
          </p>

          <div className="settings-form-grid">
            <label>
              <small className="settings-label-row">
                <span>Clé API OpenRouter</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('openrouter')}
                  className="settings-help-button"
                >
                  Obtenir une clé
                </button>
              </small>
              <input
                type="password"
                placeholder={settings?.openrouter_api_key_configured ? `Configuree (${settings.openrouter_api_key_hint})` : 'sk-or-v1-...'}
                value={secretForm.openrouter_api_key}
                onChange={(e) => updateSecret('openrouter_api_key', e.target.value)}
              />
            </label>
            <label>
              <small className="settings-label-row">
                <span>Clé API Gemini Direct</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('gemini')}
                  className="settings-help-button"
                >
                  Obtenir une clé
                </button>
              </small>
              <input
                type="password"
                placeholder={settings?.gemini_api_key_configured ? `Configuree (${settings.gemini_api_key_hint})` : 'AIzaSy...'}
                value={secretForm.gemini_api_key}
                onChange={(e) => updateSecret('gemini_api_key', e.target.value)}
              />
            </label>
          </div>

          <div className="settings-divider">
            <label>
              <small>Quand consulter l'IA (dernier recours)</small>
              <div className="live-segmented settings-segmented">
                <button
                  type="button"
                  className={form.ai_filtering_mode === 'strict' ? 'is-active' : ''}
                  onClick={() => updateField('ai_filtering_mode', 'strict')}
                >
                  Prudent — si le sujet est biblique
                </button>
                <button
                  type="button"
                  className={form.ai_filtering_mode === 'open' ? 'is-active' : ''}
                  onClick={() => updateField('ai_filtering_mode', 'open')}
                >
                  Large — à chaque phrase non résolue
                </button>
              </div>
              <span className="settings-muted-note">
                Ce réglage ne change <strong>rien</strong> à la détection locale : citations, versets lus et
                paraphrases sont toujours analysés. Il décide seulement quand l'IA est sollicitée, et
                uniquement <strong>si le moteur local n'a rien trouvé</strong>.
                <br />
                <strong>Prudent</strong> — l'IA n'est appelée que si la phrase contient un mot du registre
                biblique. <strong>Large</strong> — elle est appelée sur chaque phrase non résolue : quelques
                versets implicites en plus, au prix d'un appel de 10 à 20 s (modèle local) qui charge le
                processeur pendant le direct. Dans les deux cas, une suggestion de l'IA passe toujours par
                votre validation, jamais directement à l'écran.
              </span>
            </label>
          </div>

          <div className="settings-divider">
            <label>
              <small>
                Seuil de confiance minimal (IA) : <strong>{form.ai_confidence_threshold}%</strong>
                {form.ai_confidence_threshold >= 90 && (
                  <span className="settings-muted-note">
                    Seuil élevé : l'IA rejettera silencieusement de nombreuses suggestions pour protéger le direct.
                  </span>
                )}
              </small>
              <input
                type="range"
                min="50"
                max="99"
                value={form.ai_confidence_threshold}
                onChange={(e) => updateField('ai_confidence_threshold', Number(e.target.value))}
              />
              <span className="settings-muted-note">
                Toute suggestion IA sous ce seuil sera automatiquement rejetée pour éviter les hallucinations.
              </span>
            </label>
          </div>
        </div>
        <div data-cat="audio" className="settings-card">
          <div className="settings-card-head">
            <div>
              <span>Audio</span>
              <h2>Barrière vocale (anti-musique)</h2>
            </div>
            <label className="settings-switch">
              <input
                type="checkbox"
                checked={form.voice_gate_enabled}
                disabled={!settings?.voice_gate_available}
                onChange={(e) => updateField('voice_gate_enabled', e.target.checked)}
              />
              <span />
            </label>
          </div>
          <p>
            Filtre local (Silero VAD) qui ignore la musique, les chants et les silences avant
            transcription : moins de fausses détections pendant la louange, moins de quota consommé.
            {!settings?.voice_gate_available && ' — Modèle silero_vad.onnx absent du dossier data/.'}
          </p>
        </div>

        <div data-cat="avance" className="settings-card">
          <span>Avant le culte</span>
          <h2>Mode répétition</h2>
          <p className="settings-rehearsal-copy">
            Collez un extrait de prédication : la chaîne de détection est rejouée comme en direct,
            sans rien projeter.
          </p>
          <textarea
            value={rehearseText}
            onChange={(e) => setRehearseText(e.target.value)}
            placeholder="Ex : ce matin nous lisons dans jean chapitre trois verset seize car dieu a tant aimé le monde…"
            rows={3}
          />
          <button
            type="button"
            className="vp-btn vp-btn--sm"
            onClick={runRehearsal}
            disabled={rehearsing || !rehearseText.trim()}
          >
            {rehearsing ? 'Analyse…' : 'Tester la détection'}
          </button>
          {rehearseResults !== null && (
            <div className="settings-result-list">
              {rehearseResults.length === 0 ? (
                <span className="settings-secret-hint">Aucune référence détectée dans ce texte.</span>
              ) : (
                rehearseResults.map((d, i) => (
                  <div key={i} className="settings-result-row">
                    <strong>{d.reference}</strong>
                    <span>{d.detection_method}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </section>

      {versionInfo && onglet === 'avance' && (
        <section className="settings-section">
          <div className="settings-section-head">
            <span className="settings-eyebrow">à propos</span>
            <h2>Version installée</h2>
          </div>
          <div className="settings-section-body">
            <p className="text-sm">
              VersePro <strong>{versionInfo.current}</strong> — Selah Studios.
              {' '}
              {versionInfo.update_available
                ? <>Une version <strong>{versionInfo.latest}</strong> est disponible.</>
                : versionInfo.checked
                  ? 'Vous êtes à jour.'
                  : 'Le contrôle des mises à jour n\'est pas activé — rien n\'est envoyé sur internet.'}
            </p>
            {versionInfo.update_available && versionInfo.url && (
              <p className="text-sm" style={{ marginTop: '8px' }}>
                {versionInfo.notes ? <span>{versionInfo.notes} </span> : null}
                <a href={versionInfo.url} target="_blank" rel="noreferrer">Télécharger la mise à jour</a>
                {' '}— l'installation reste manuelle : VersePro ne se remplace jamais tout seul.
              </p>
            )}
          </div>
        </section>
      )}

      <div className="settings-footer">
        <div>
          <strong>{savedAt ? 'Paramètres sauvegardés' : 'Prêt à sauvegarder'}</strong>
          <span>{savedAt ? savedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : 'Les changements seront appliques au backend.'}</span>
        </div>
        <button onClick={save} disabled={saving}>
          {saving ? 'Sauvegarde...' : 'Sauvegarder'}
        </button>
      </div>

      {helpModal && (
        <div className="vp-modal-backdrop">
          <div className="vp-modal settings-modal">
            <h3 className="settings-modal-title">
              {helpModal === 'deepgram' && 'Obtenir une clé API Deepgram'}
              {helpModal === 'openrouter' && 'Obtenir une clé API OpenRouter'}
              {helpModal === 'gemini' && 'Obtenir une clé API Gemini Direct'}
            </h3>
            
            <div className="settings-modal-body">
              {helpModal === 'deepgram' && (
                <ol className="settings-modal-list">
                  <li>Allez sur le site <strong><a href="https://console.deepgram.com" target="_blank" rel="noreferrer" >console.deepgram.com</a></strong> et créez un compte.</li>
                  <li>Ouvrez la section <strong>"API Keys"</strong>, puis créez une nouvelle clé.</li>
                  <li>Sélectionnez le rôle d'administrateur ou d'écriture, nommez la clé "VersePro", puis cliquez sur créer.</li>
                  <li>Copiez la clé générée (elle commence par <code>dg_</code>) et collez-la dans le champ correspondant dans VersePro.</li>
                </ol>
              )}
              {helpModal === 'openrouter' && (
                <ol className="settings-modal-list">
                  <li>Allez sur <strong><a href="https://openrouter.ai" target="_blank" rel="noreferrer" >openrouter.ai</a></strong> et inscrivez-vous.</li>
                  <li>Dans votre compte, allez dans la section <strong>"Keys"</strong> (ou Clés API).</li>
                  <li>Créez une nouvelle clé API et nommez-la "VersePro".</li>
                  <li>Copiez la clé (elle commence par <code>sk-or-v1-</code>) et collez-la dans VersePro.</li>
                </ol>
              )}
              {helpModal === 'gemini' && (
                <ol className="settings-modal-list">
                  <li>Allez sur <strong><a href="https://aistudio.google.com" target="_blank" rel="noreferrer" >aistudio.google.com</a></strong> avec votre compte Google.</li>
                  <li>Cliquez sur <strong>"Get API Key"</strong> en haut à gauche.</li>
                  <li>Créez une clé dans un nouveau projet ou un projet existant.</li>
                  <li>Copiez la clé générée (elle commence par <code>AIzaSy</code>) et collez-la dans VersePro.</li>
                </ol>
              )}
            </div>
            
            <button
              onClick={() => setHelpModal(null)}
              className="vp-btn vp-btn--primary settings-modal-close"
            >
              Compris, fermer
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
