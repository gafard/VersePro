import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store.js'
import { shallow } from 'zustand/shallow'
import { BACKEND_BASE, isTauri } from '../env.js'
import OverlayEditor from './OverlayEditor.jsx'
import BibleImport from './BibleImport.jsx'

// --- Modern Vector SVG Icons ---
const IconActivity = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
)

const IconMic = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="22" />
  </svg>
)

const IconCpu = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
    <rect x="9" y="9" width="6" height="6" />
    <line x1="9" y1="1" x2="9" y2="4" />
    <line x1="15" y1="1" x2="15" y2="4" />
    <line x1="9" y1="20" x2="9" y2="23" />
    <line x1="15" y1="20" x2="15" y2="23" />
    <line x1="20" y1="9" x2="23" y2="9" />
    <line x1="20" y1="15" x2="23" y2="15" />
    <line x1="1" y1="9" x2="4" y2="9" />
    <line x1="1" y1="15" x2="4" y2="15" />
  </svg>
)

const IconMonitor = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
)

const IconRadio = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="2" />
    <path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.83a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14" />
  </svg>
)

const IconSliders = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="4" y1="21" x2="4" y2="14" />
    <line x1="4" y1="10" x2="4" y2="3" />
    <line x1="12" y1="21" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12" y2="3" />
    <line x1="20" y1="21" x2="20" y2="16" />
    <line x1="20" y1="12" x2="20" y2="3" />
    <line x1="1" y1="14" x2="7" y2="14" />
    <line x1="9" y1="8" x2="15" y2="8" />
    <line x1="17" y1="16" x2="23" y2="16" />
  </svg>
)

const IconShield = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
)

const IconCloud = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
  </svg>
)

const IconSparkles = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
  </svg>
)

const IconPalette = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="13.5" cy="6.5" r=".5" fill={color} />
    <circle cx="17.5" cy="10.5" r=".5" fill={color} />
    <circle cx="8.5" cy="7.5" r=".5" fill={color} />
    <circle cx="6.5" cy="12.5" r=".5" fill={color} />
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.92 0 1.7-.72 1.7-1.61 0-.43-.17-.83-.44-1.14-.24-.28-.39-.64-.39-1.05 0-.88.72-1.6 1.6-1.6H16c3.3 0 6-2.7 6-6 0-5.5-4.5-10-10-10z" />
  </svg>
)

const IconBook = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
)

const IconFlask = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55A2 2 0 0 0 6.508 23h10.984a2 2 0 0 0 1.788-2.45l-5.069-10.127A2 2 0 0 1 14 9.527V2" />
    <line x1="8.5" y1="2" x2="15.5" y2="2" />
    <line x1="7" y1="16" x2="17" y2="16" />
  </svg>
)

const IconInfo = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
)

const IconClipboard = ({ size = 18, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
  </svg>
)

const IconSave = ({ size = 16, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
    <polyline points="17 21 17 13 7 13 7 21" />
    <polyline points="7 3 7 8 15 8" />
  </svg>
)

const IconChevron = ({ size = 16, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
)

/** Accordion section — click header to expand/collapse */
function Accordion({ title, icon, description, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`settings-accordion${open ? ' is-open' : ''}`}>
      <button type="button" className="settings-accordion-header" onClick={() => setOpen(!open)}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && <span className="accordion-icon">{icon}</span>}
          {title}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {badge}
          <span className="accordion-chevron"><IconChevron /></span>
        </span>
      </button>
      <div className="settings-accordion-body">
        {description && <p className="settings-accordion-desc">{description}</p>}
        {children}
      </div>
    </div>
  )
}

/** Row — label+desc left, control right */
function Row({ label, desc, tooltip, children }) {
  return (
    <div className="settings-row">
      <div className="settings-row-info">
        <span className="settings-row-label">
          {label}
          {tooltip && <span className="settings-info-icon" title={tooltip}>i</span>}
        </span>
        {desc && <span className="settings-row-desc">{desc}</span>}
      </div>
      <div className="settings-row-control">{children}</div>
    </div>
  )
}

/** Reusable progress bar */
function ProgressBar({ percent, status }) {
  return (
    <div className="settings-progress-wrapper">
      <div className="settings-progress-info">
        <span>{status}</span>
        <span>{Math.round(percent)}%</span>
      </div>
      <div className="settings-progress-track">
        <div className="settings-progress-fill" style={{ width: `${Math.max(2, percent)}%` }} />
      </div>
    </div>
  )
}

// Regroupement des réglages. L'ordre suit celui d'une mise en route : on
// branche le micro, on choisit les moteurs, on règle ce qui s'affiche, on
// connecte les sorties, et le reste ne sert qu'occasionnellement.
const ONGLETS = [
  { cle: 'general', nom: 'Général', note: 'statuts, système' },
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

function getIconForTab(cle) {
  switch (cle) {
    case 'general': return <IconActivity size={16} />
    case 'audio': return <IconMic size={16} />
    case 'moteurs': return <IconSparkles size={16} />
    case 'projection': return <IconMonitor size={16} />
    case 'sorties': return <IconRadio size={16} />
    case 'avance': return <IconSliders size={16} />
    default: return <IconInfo size={16} />
  }
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
    prepareLocalAsr,
    connected,
    connectionStatus,
    audioDevices,
    selectedAudioDeviceId,
    setSelectedAudioDeviceId,
    refreshAudioDevices,
    audioFilterMode,
    setAudioFilterMode,
    setSelectedEngine,
    desktopUpdateInfo,
    desktopUpdateStatus,
    desktopUpdateError,
    checkDesktopUpdate,
    openDesktopUpdate
  } = useStore(s => ({
    settings: s.settings,
    fetchSettings: s.fetchSettings,
    updateSettings: s.updateSettings,
    availableBibles: s.availableBibles,
    fetchBibles: s.fetchBibles,
    activeBible: s.activeBible,
    aiActive: s.aiActive,
    propresenterConnected: s.propresenterConnected,
    addToast: s.addToast,
    asrStatus: s.asrStatus,
    semanticStatus: s.semanticStatus,
    fetchIntelligenceStatus: s.fetchIntelligenceStatus,
    prepareSemanticIndex: s.prepareSemanticIndex,
    prepareLocalAsr: s.prepareLocalAsr,
    connected: s.connected,
    connectionStatus: s.connectionStatus,
    audioDevices: s.audioDevices,
    selectedAudioDeviceId: s.selectedAudioDeviceId,
    setSelectedAudioDeviceId: s.setSelectedAudioDeviceId,
    refreshAudioDevices: s.refreshAudioDevices,
    audioFilterMode: s.audioFilterMode,
    setAudioFilterMode: s.setAudioFilterMode,
    setSelectedEngine: s.setSelectedEngine,
    desktopUpdateInfo: s.desktopUpdateInfo,
    desktopUpdateStatus: s.desktopUpdateStatus,
    desktopUpdateError: s.desktopUpdateError,
    checkDesktopUpdate: s.checkDesktopUpdate,
    openDesktopUpdate: s.openDesktopUpdate
  }), shallow)

  const prepareReference = useStore(s => s.prepareReference)
  const [sermonText, setSermonText] = useState('')
  const [extractingNotes, setExtractingNotes] = useState(false)
  const [sermonExtracted, setSermonExtracted] = useState([])

  const handleExtractSermonNotes = async () => {
    if (!sermonText.trim()) return
    setExtractingNotes(true)
    try {
      const res = await fetch(`${BACKEND_BASE}/api/v1/bibles/extract_references`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sermonText }),
      })
      const data = await res.json()
      if (data.references && data.references.length > 0) {
        setSermonExtracted(data.references)
        addToast?.({ message: `✅ ${data.count} verset(s) extrait(s) des notes !`, kind: 'success' })
      } else {
        setSermonExtracted([])
        addToast?.({ message: "⚠️ Aucun verset biblique explicite n'a été trouvé.", kind: 'warn' })
      }
    } catch (err) {
      console.error('Erreur extraction notes:', err)
      addToast?.({ message: "❌ Erreur lors de l'extraction des versets.", kind: 'error' })
    } finally {
      setExtractingNotes(false)
    }
  }

  const handleAddAllSermonVerses = () => {
    sermonExtracted.forEach((item) => {
      if (prepareReference) prepareReference(item.reference)
    })
    addToast?.({ message: `📥 ${sermonExtracted.length} verset(s) ajoutés au déroulé !`, kind: 'success' })
  }

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
  const [aiTab, setAiTab] = useState('cloud')

  // Version installée et, si un manifeste est configuré, disponibilité d'une
  // mise à jour. L'appel échoue en silence : hors ligne, la section affiche
  // simplement la version installée.
  const [legacyVersionInfo, setLegacyVersionInfo] = useState(null)
  useEffect(() => {
    if (isTauri) {
      checkDesktopUpdate({ silent: true })
      return undefined
    }
    let vivant = true
    fetch(`${BACKEND_BASE}/api/v1/update/check`)
      .then((r) => r.json())
      .then((d) => { if (vivant) setLegacyVersionInfo(d) })
      .catch(() => {})
    return () => { vivant = false }
  }, [checkDesktopUpdate])
  const versionInfo = isTauri
    ? (desktopUpdateInfo.current ? desktopUpdateInfo : null)
    : legacyVersionInfo
  const [rehearseText, setRehearseText] = useState('')
  const [rehearseResults, setRehearseResults] = useState(null)
  const [rehearsing, setRehearsing] = useState(false)
  const [preparingLocal, setPreparingLocal] = useState('')
  // Suivi du téléchargement du modèle local (Ollama pull)
  const [pullProgress, setPullProgress] = useState(null) // null | { status, percent, error, done }
  // Onglets de la console : onze cartes d'affilée obligeaient à faire défiler
  // longtemps pour trouver un réglage. L'onglet est mémorisé — un bénévole qui
  // revient tombe là où il s'était arrêté.
  const [onglet, setOnglet] = useState(() => {
    try { return localStorage.getItem('versepro_settings_tab') || 'general' } catch { return 'general' }
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
      if (kind === 'nemotron') {
        await prepareLocalAsr()
        addToast({ message: 'Téléchargement du moteur local lancé (716 Mo)', kind: 'success' })
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
    <div className="settings-page vp-settings-layout">
      {/* Barre latérale (Sidebar) */}
      <aside className="vp-settings-sidebar">
        <div className="vp-settings-sidebar-header">
          <h2>SETTINGS</h2>
        </div>
        <nav className="vp-settings-nav" aria-label="Onglets de configuration">
          {ONGLETS.map(({ cle, nom, note }) => (
            <button
              key={cle}
              type="button"
              className={`vp-settings-nav-item ${onglet === cle ? 'is-active' : ''}`}
              onClick={() => changerOnglet(cle)}
            >
              <span className="vp-settings-nav-icon">{getIconForTab(cle)}</span>
              <div className="vp-settings-nav-text">
                <span className="vp-settings-nav-label">{nom}</span>
              </div>
            </button>
          ))}
        </nav>
      </aside>

      {/* Contenu principal */}
      <main className="vp-settings-main">
        <div className="vp-settings-main-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h1>{ONGLETS.find(o => o.cle === onglet)?.nom || 'Réglages'}</h1>
            <p className="vp-settings-main-subtitle">{ONGLETS.find(o => o.cle === onglet)?.note}</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {savedAt && (
              <span style={{ fontSize: '12px', color: 'var(--vp-ok, #22c55e)', fontWeight: 600 }}>
                ✓ Enregistré à {savedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
            <button
              onClick={save}
              disabled={saving}
              style={{
                background: 'var(--vp-accent, #0ea5e9)',
                color: '#fff',
                fontWeight: 700,
                fontSize: '13px',
                padding: '10px 20px',
                borderRadius: '8px',
                border: 'none',
                cursor: saving ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 2px 8px rgba(14, 165, 233, 0.3)'
              }}
            >
              <IconSave size={16} />
              {saving ? 'Sauvegarde...' : 'Sauvegarder'}
            </button>
          </div>
        </div>

        <section className="settings-grid" data-active={onglet}>

          {/* TAB 1: GENERAL */}
          <div data-cat="general">
            <Accordion
              title="État du système"
              icon={<IconActivity color="#0ea5e9" />}
              description="Vue d'ensemble de la connexion serveur, ProPresenter et IA."
              defaultOpen={true}
            >
              <div className="settings-status-grid">
                {statusCards.map((card) => (
                  <div key={card.label} className={`settings-status-card is-${card.tone}`}>
                    <span>{card.label}</span>
                    <strong>{card.value}</strong>
                  </div>
                ))}
              </div>
            </Accordion>
          </div>

          {/* TAB 2: AUDIO */}
          <div data-cat="audio">
            <Accordion
              title="Entrée micro"
              icon={<IconMic color="#0ea5e9" />}
              description="Sélectionnez le micro et le mode de filtrage adapté à votre environnement."
              defaultOpen={true}
            >
              <Row label="Source audio">
                <div style={{ display: 'flex', gap: '8px' }}>
                  {/* Le défaut système reste toujours atteignable : c'est la
                      sortie de secours quand une entrée choisie s'est révélée
                      muette en plein culte. */}
                  <select value={selectedAudioDeviceId} onChange={(e) => updateAudioDevice(e.target.value)}>
                    <option value="">Entrée par défaut du système</option>
                    {audioDevices.map((device, index) => (
                      <option key={device.deviceId || index} value={device.deviceId}>
                        {device.label || `Micro ${index + 1}`}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="vp-btn vp-btn--ghost vp-btn--sm" onClick={refreshAudioDevices}>
                    Actualiser
                  </button>
                </div>
              </Row>
              <Row label="Prétraitement audio">
                <select value={audioFilterMode} onChange={(e) => setAudioFilterMode(e.target.value)}>
                  <option value="off">Signal brut (recommandé)</option>
                  <option value="speech">Parole: 80 Hz à 8 kHz</option>
                  <option value="church">Église avec musique: 120 Hz à 7 kHz</option>
                </select>
              </Row>
            </Accordion>

            <Accordion
              title="Barrière vocale (anti-musique)"
              icon={<IconShield color="#0ea5e9" />}
              description={`Détection Silero VAD : bloque les segments musicaux pour ne transcrire que la voix.${!settings?.voice_gate_available ? ' — Modèle silero_vad.onnx absent du dossier data/.' : ''}`}
            >
              <Row label="Activer la barrière">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    aria-label="Activer la barrière vocale anti-musique"
                    checked={form.voice_gate_enabled}
                    disabled={!settings?.voice_gate_available}
                    onChange={(e) => updateField('voice_gate_enabled', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>
            </Accordion>
          </div>

          {/* TAB 3: MOTEURS */}
          <div data-cat="moteurs">
            <Accordion title="Transcription" icon={<IconCpu color="#0ea5e9" />} defaultOpen={true}>
              <Row label="Moteur par défaut">
                <select value={form.asr_default_engine} onChange={(e) => {
                  const val = e.target.value
                  updateField('asr_default_engine', val)
                  setSelectedEngine(val)
                }}>
                  <option value="auto">Auto (Deepgram Cloud puis Nemotron local)</option>
                  <option value="deepgram">Deepgram Cloud (Rapide &lt; 0.5 s)</option>
                  <option value="nemotron">Nemotron 3.5-ASR 0.6B (Recommandé Local, 716 Mo)</option>
                  <option value="vosk">Vosk local (Secours)</option>
                </select>
              </Row>

              <div className="settings-divider">
                <div className="settings-card-head">
                  <div>
                    <small>Nemotron 3.5-ASR local</small>
                    <p>
                      {asrStatus?.nemotron?.ready
                        ? 'Prêt · décodage en flux, hors ligne'
                        : asrStatus?.nemotron?.downloading
                          ? `Téléchargement en cours · ${Math.round((asrStatus.nemotron.download_progress || 0) * 100)} %`
                          : `Non préparé · ${asrStatus?.nemotron?.model_size_mb || 716} Mo à télécharger`}
                    </p>
                  </div>
                  <span className={`vp-chip ${asrStatus?.nemotron?.ready ? 'is-ok' : ''}`}>
                    {asrStatus?.nemotron?.ready ? 'Prêt' : 'Optionnel'}
                  </span>
                </div>
                {asrStatus?.nemotron?.last_error && !asrStatus?.nemotron?.ready && (
                  <span className="settings-error-note" role="alert">
                    Échec : {asrStatus.nemotron.last_error}
                  </span>
                )}
                {asrStatus?.nemotron?.downloading && <ProgressBar percent={Math.round((asrStatus.nemotron.download_progress || 0) * 100)} status="Téléchargement Nemotron 3.5-ASR…" />}
                <button
                  type="button"
                  className="vp-btn vp-btn--sm"
                  onClick={() => prepareLocalEngine('nemotron')}
                  disabled={preparingLocal === 'nemotron' || asrStatus?.nemotron?.downloading}
                >
                  {asrStatus?.nemotron?.ready ? 'Moteur local prêt' : 'Préparer le moteur local'}
                </button>
                <span className="settings-muted-note">
                  Décodage en flux, sans Internet. Plus précis que Vosk sur les accents,
                  pour 716 Mo téléchargés une seule fois.
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
                </div>
                {semanticStatus?.last_error && !semanticStatus?.installed && (
                  <span className="settings-error-note" role="alert">
                    Échec : {semanticStatus.last_error}
                  </span>
                )}
                {(semanticStatus?.downloading || semanticStatus?.indexing) && <ProgressBar percent={semanticStatus?.download_progress || 0} status={semanticStatus?.downloading ? 'Téléchargement du modèle…' : 'Indexation des versets…'} />}
                <button type="button" className="vp-btn vp-btn--sm" onClick={() => prepareLocalEngine('semantic')} disabled={preparingLocal === 'semantic' || semanticStatus?.indexing}>
                  {semanticStatus?.installed ? 'Réindexer' : semanticStatus?.indexing ? 'Indexation…' : 'Installer et indexer'}
                </button>
                <span className="settings-muted-note">
                  Première préparation uniquement : plusieurs minutes selon le processeur. Elle ne démarre jamais pendant le live sans votre action.
                </span>
              </div>

              <Row label="Recherche sémantique">
                <label className="settings-switch">
                  <input type="checkbox" checked={form.local_semantic_enabled} onChange={(e) => updateField('local_semantic_enabled', e.target.checked)} />
                  <span />
                </label>
              </Row>
              <Row label="Seuil sémantique">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <input type="range" min="0.50" max="0.95" step="0.005" value={form.local_semantic_threshold} onChange={(e) => updateField('local_semantic_threshold', Number(e.target.value))} />
                  <span className="settings-muted-note">
                    {Math.round(form.local_semantic_threshold * 100)} %
                  </span>
                </div>
              </Row>
            </Accordion>

            <Accordion title="Transcription Cloud (Deepgram)" icon={<IconCloud color="#0ea5e9" />}>
              <Row label="Modèle">
                <select value={form.deepgram_model} onChange={(e) => updateField('deepgram_model', e.target.value)}>
                  <option value="nova-2">nova-2</option>
                  <option value="nova-3">nova-3</option>
                  <option value="base">base</option>
                  <option value="enhanced">enhanced</option>
                </select>
              </Row>
              <Row label="Langue">
                <select value={form.deepgram_language} onChange={(e) => updateField('deepgram_language', e.target.value)}>
                  <option value="fr">Français</option>
                  <option value="en">Anglais</option>
                  <option value="es">Espagnol</option>
                  <option value="pt">Portugais</option>
                </select>
              </Row>
              <Row label="Clé API Deepgram">
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="password"
                    placeholder={settings?.deepgram_api_key_configured ? `Configurée (${settings.deepgram_api_key_hint})` : 'Coller une clé Deepgram'}
                    value={secretForm.deepgram_api_key}
                    onChange={(e) => updateSecret('deepgram_api_key', e.target.value)}
                  />
                  <button type="button" onClick={() => setHelpModal('deepgram')} className="settings-help-button">
                    Obtenir
                  </button>
                </div>
              </Row>
            </Accordion>

            <Accordion title="Détection intelligente" icon={<IconSparkles color="#0ea5e9" />} defaultOpen={true}>
              <Row label="Activer">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={form.ai_agent_enabled}
                    onChange={(e) => updateField('ai_agent_enabled', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>

              <div className="live-segmented settings-segmented-sv mt-4 mb-6" style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  className={aiTab === 'cloud' ? 'is-active flex-1 py-2 font-bold' : 'flex-1 py-2'}
                  onClick={() => setAiTab('cloud')}
                >
                  ☁️ Cloud (Recommandé)
                </button>
                <button
                  type="button"
                  className={aiTab === 'local' ? 'is-active flex-1 py-2 font-bold' : 'flex-1 py-2'}
                  onClick={() => setAiTab('local')}
                >
                  💻 Local (Hors-ligne)
                </button>
              </div>

              {aiTab === 'cloud' && (
                <div className="animate-fade-in space-y-4">
                  <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3 text-emerald-400">
                      <span>☁️</span>
                      <span className="font-bold text-sm">IA Cloud VersePro</span>
                    </div>
                    <span className="text-xs font-bold text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded">✅ Connecté</span>
                  </div>

                  <div>
                    <Row label="Clé API Gemini (Gratuit)">
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <input
                          type="password"
                          placeholder={settings?.gemini_api_key_configured ? `Configurée (${settings.gemini_api_key_hint})` : 'AIzaSy...'}
                          value={secretForm.gemini_api_key}
                          onChange={(e) => updateSecret('gemini_api_key', e.target.value)}
                        />
                        <button type="button" onClick={() => setHelpModal('gemini')} className="settings-help-button">Obtenir</button>
                      </div>
                    </Row>
                    <Row label="Clé API OpenRouter">
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <input
                          type="password"
                          placeholder={settings?.openrouter_api_key_configured ? `Configurée (${settings.openrouter_api_key_hint})` : 'sk-or-v1-...'}
                          value={secretForm.openrouter_api_key}
                          onChange={(e) => updateSecret('openrouter_api_key', e.target.value)}
                        />
                        <button type="button" onClick={() => setHelpModal('openrouter')} className="settings-help-button">Obtenir</button>
                      </div>
                    </Row>
                  </div>
                  <p className="text-xs text-text-dim mt-2">
                    VersePro utilise Gemini 1.5 Flash par défaut (15 requêtes/min gratuites).
                  </p>
                </div>
              )}

              {aiTab === 'local' && (
                <div className="animate-fade-in space-y-4">
                  <div className="p-4 rounded-xl bg-surface-2 border border-white/10 flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3 text-text-strong">
                      <span>💻</span>
                      <span className="font-bold text-sm">Ollama (Moteur Local)</span>
                    </div>
                    <span className="text-xs font-bold text-text-dim bg-surface-3 px-2 py-1 rounded">Modèle: llama3.1:8b</span>
                  </div>

                  <div className="p-4 bg-accent/10 border border-accent/20 rounded-xl">
                    <h4 className="text-sm font-bold text-accent mb-2">Exécution Hors-Ligne</h4>
                    <p className="text-xs text-text-dim mb-4 leading-relaxed">
                      L'IA locale nécessite que le logiciel <a href="https://ollama.com" target="_blank" rel="noreferrer" className="underline hover:text-accent">Ollama</a> soit installé et lancé sur votre ordinateur.
                      VersePro utilise le modèle <strong>Llama 3.1 8B</strong> (~4.7 Go).
                    </p>

                    {!pullProgress ? (
                      <button
                        className="vp-btn vp-btn--primary w-full text-sm py-3 font-bold"
                        onClick={() => {
                          setPullProgress({ status: 'Connexion à Ollama…', percent: 0 })
                          const es = new EventSource(`${BACKEND_BASE}/api/v1/ai/pull-local-model`)
                          es.onmessage = (ev) => {
                            try {
                              const d = JSON.parse(ev.data)
                              if (d.error) {
                                setPullProgress({ status: d.error, percent: 0, error: true })
                                es.close()
                                return
                              }
                              if (d.status === 'done' || d.percent >= 100) {
                                setPullProgress({ status: 'Installation terminée !', percent: 100, done: true })
                                addToast?.({ message: '✅ Llama 3.1 installé avec succès ! Redémarrez VersePro pour activer le mode local.', kind: 'success' })
                                es.close()
                                return
                              }
                              let label = d.status || ''
                              if (label.startsWith('pulling')) label = 'Téléchargement…'
                              else if (label.startsWith('verifying')) label = 'Vérification…'
                              else if (label.startsWith('writing')) label = 'Écriture…'
                              setPullProgress({ status: label, percent: d.percent || 0 })
                            } catch {}
                          }
                          es.onerror = () => {
                            setPullProgress(prev => prev?.done ? prev : { status: 'Connexion perdue. Ollama est-il lancé ?', percent: 0, error: true })
                            es.close()
                          }
                        }}
                      >
                        📥 Installer l'Intelligence Biblique (Llama 3.1)
                      </button>
                    ) : pullProgress.error ? (
                      <div>
                        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-center mb-3">
                          <p className="text-xs text-red-400 font-bold">❌ {pullProgress.status}</p>
                        </div>
                        <button
                          className="vp-btn vp-btn--primary w-full text-sm py-2"
                          onClick={() => setPullProgress(null)}
                        >
                          🔄 Réessayer
                        </button>
                      </div>
                    ) : pullProgress.done ? (
                      <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-center">
                        <p className="text-sm text-emerald-400 font-bold">✅ {pullProgress.status}</p>
                        <p className="text-[10px] text-text-dim mt-1">Le moteur local est prêt à l'emploi.</p>
                      </div>
                    ) : (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs text-text-dim">{pullProgress.status}</span>
                          <span className="text-xs font-bold text-accent">{pullProgress.percent.toFixed(0)}%</span>
                        </div>
                        <div className="w-full h-3 rounded-full bg-surface-3 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${pullProgress.percent}%`,
                              background: 'linear-gradient(90deg, var(--accent), var(--accent-bright, #60a5fa))',
                            }}
                          />
                        </div>
                        <p className="text-[10px] text-text-dim mt-2 text-center opacity-70">
                          Ne fermez pas cette page pendant le téléchargement.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="settings-divider" style={{ marginTop: '24px' }}>
                <Row label="Mode de consultation IA">
                  <div className="live-segmented settings-segmented">
                    <button
                      type="button"
                      className={form.ai_filtering_mode === 'strict' ? 'is-active' : ''}
                      onClick={() => updateField('ai_filtering_mode', 'strict')}
                    >
                      Prudent
                    </button>
                    <button
                      type="button"
                      className={form.ai_filtering_mode === 'open' ? 'is-active' : ''}
                      onClick={() => updateField('ai_filtering_mode', 'open')}
                    >
                      Large
                    </button>
                  </div>
                </Row>
                <Row label="Seuil de confiance IA">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <input
                      type="range"
                      min="50"
                      max="99"
                      value={form.ai_confidence_threshold}
                      onChange={(e) => updateField('ai_confidence_threshold', Number(e.target.value))}
                    />
                    <span className="settings-muted-note">
                      {form.ai_confidence_threshold}%
                    </span>
                  </div>
                </Row>
              </div>
            </Accordion>
          </div>

          {/* TAB 4: PROJECTION */}
          <div data-cat="projection">
            <Accordion title="Diffusion en direct" icon={<IconMonitor color="#0ea5e9" />} description="Contrôle comment les versets sont envoyés à l'écran." defaultOpen={true}>
              <Row label="Envoi automatique">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={form.auto_send}
                    onChange={(e) => updateField('auto_send', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>
              <Row label="Mode dimanche sûr" desc="Bloque toute projection automatique.">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={form.sunday_safe_mode}
                    onChange={(e) => updateField('sunday_safe_mode', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>
              <Row label="Mode ombre" desc="Analyse le culte sans piloter les sorties.">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={form.shadow_mode}
                    onChange={(e) => updateField('shadow_mode', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>
            </Accordion>

            <Accordion title="Thèmes & Personnalisation" icon={<IconPalette color="#0ea5e9" />}>
              <Row label="Thème d'affichage">
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
              </Row>
              <Row label="Style Lower-Third">
                {form.projection_theme === 'broadcast' ? (
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
                ) : (
                  <select disabled value="default">
                    <option value="default">Indisponible avec ce thème</option>
                  </select>
                )}
              </Row>

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

              <div className="settings-divider">
                <div className="settings-card-head">
                  <div>
                    <small>Atelier d'habillage</small>
                  </div>
                </div>
                <OverlayEditor />
              </div>

              <Row label="Afficher version Bible">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={form.show_bible_version}
                    onChange={(e) => updateField('show_bible_version', e.target.checked)}
                  />
                  <span />
                </label>
              </Row>

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
              </div>
            </Accordion>

            <Accordion title="Bible" icon={<IconBook color="#0ea5e9" />}>
              <Row label="Version projetée">
                <select value={form.bible_version} onChange={(e) => updateField('bible_version', e.target.value)}>
                  {availableBibles.map((code) => (
                    <option key={code} value={code}>
                      {code} - {BIBLE_NAMES[code] || code}
                    </option>
                  ))}
                </select>
              </Row>
              <BibleImport />
            </Accordion>
          </div>

          {/* TAB 5: SORTIES */}
          <div data-cat="sorties">
            <Accordion
              title="NDI"
              icon={<IconRadio color="#0ea5e9" />}
              description={settings?.ndi?.sending ? 'À l\'antenne' : settings?.ndi?.available ? 'Prêt' : 'Non détecté'}
              badge={<span className={`vp-chip ${settings?.ndi?.sending ? 'is-ok' : settings?.ndi?.available ? '' : 'is-warn'}`}>
                {settings?.ndi?.sending ? 'À l\'antenne' : settings?.ndi?.available ? 'Prêt' : 'Non détecté'}
              </span>}
              defaultOpen={true}
            >
              {settings?.ndi?.available ? (
                <>
                  <Row label="Activer NDI">
                    <label className="settings-switch">
                      <input
                        type="checkbox"
                        checked={form.ndi_enabled}
                        onChange={(e) => updateField('ndi_enabled', e.target.checked)}
                      />
                      <span />
                    </label>
                  </Row>
                  <Row label="Nom de la source">
                    <input
                      type="text"
                      value={form.ndi_source_name}
                      onChange={(e) => updateField('ndi_source_name', e.target.value)}
                      placeholder="VersePro"
                    />
                  </Row>
                  {settings?.ndi?.sending && (
                    <div className="flex items-center gap-2 mt-2 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                      <span className="text-emerald-400 text-xs font-semibold">● NDI actif — visible sur le réseau local</span>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col gap-3 p-3.5 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-200">
                  <div>
                    <strong>NDI Runtime (Vizrt) non détecté sur ce poste.</strong>
                    {settings?.ndi?.last_error ? <span className="block text-xs mt-1 opacity-70">{settings.ndi.last_error}</span> : null}
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    NDI permet d'envoyer l'écran de projection en direct sur le réseau local (OBS, vMix, Resolume…).
                    Installez le Runtime NDI gratuit, redémarrez VersePro, et la sortie NDI sera disponible.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <a href="https://ndi.video/tools/ndi-core-suite/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-xs text-amber-400 underline font-medium hover:text-amber-300 w-fit">
                      ⬇ Télécharger NDI Core Suite (Windows) ↗
                    </a>
                    <a href="https://ndi.video/tools/ndi-core-suite/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-xs text-sky-400 underline font-medium hover:text-sky-300 w-fit">
                      ⬇ Télécharger NDI Core Suite (macOS) ↗
                    </a>
                  </div>
                </div>
              )}
            </Accordion>

            <Accordion title="ProPresenter" icon={<IconMonitor color="#0ea5e9" />}>
              <Row label="Hôte">
                <input
                  type="text"
                  value={form.propresenter_host}
                  onChange={(e) => updateField('propresenter_host', e.target.value)}
                />
              </Row>
              <Row label="Port">
                <input
                  type="number"
                  value={form.propresenter_port}
                  onChange={(e) => updateField('propresenter_port', e.target.value)}
                />
              </Row>
              <Row label="Nom du message">
                <input
                  type="text"
                  value={form.propresenter_message_name}
                  onChange={(e) => updateField('propresenter_message_name', e.target.value)}
                />
              </Row>
            </Accordion>
          </div>

          {/* TAB 6: AVANCE */}
          <div data-cat="avance">
            <Accordion title="📋 Notes du Sermon & Extraction" icon={<IconClipboard color="#0ea5e9" />} description="Collez le texte de votre prédication pour en extraire automatiquement tous les versets et les ajouter au déroulé." defaultOpen={true}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <textarea
                  value={sermonText}
                  onChange={(e) => setSermonText(e.target.value)}
                  placeholder="Collez ici votre prédication ou vos notes de sermon (ex: Dimanche nous lirons Jean 3:16 et Psaume 23:1...)"
                  rows={5}
                  style={{
                    width: '100%',
                    background: 'var(--vp-bg-raised)',
                    border: '1px solid var(--vp-border-strong)',
                    borderRadius: 'var(--vp-radius)',
                    color: 'var(--vp-text)',
                    fontSize: '13px',
                    padding: '10px',
                    fontFamily: 'var(--vp-font)'
                  }}
                />
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button
                    type="button"
                    className="vp-btn vp-btn--primary"
                    onClick={handleExtractSermonNotes}
                    disabled={extractingNotes || !sermonText.trim()}
                  >
                    {extractingNotes ? 'Extraction…' : '🔍 Extraire les versets'}
                  </button>
                  {sermonExtracted.length > 0 && (
                    <button
                      type="button"
                      className="vp-btn vp-btn--secondary"
                      onClick={handleAddAllSermonVerses}
                    >
                      📥 Ajouter tous au déroulé ({sermonExtracted.length})
                    </button>
                  )}
                </div>

                {sermonExtracted.length > 0 && (
                  <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <span style={{ fontSize: '12.5px', fontWeight: '700', color: 'var(--vp-text)' }}>
                      {sermonExtracted.length} verset(s) extrait(s) :
                    </span>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '8px' }}>
                      {sermonExtracted.map((item, idx) => (
                        <div key={idx} style={{ background: 'var(--vp-bg-elevated)', border: '1px solid var(--vp-border)', padding: '8px 12px', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong style={{ fontSize: '12.5px', color: 'var(--vp-text)' }}>{item.reference}</strong>
                          <button
                            type="button"
                            className="vp-btn vp-btn--ghost vp-btn--sm"
                            onClick={() => {
                              if (prepareReference) prepareReference(item.reference)
                              addToast?.({ message: `Ajouté : ${item.reference}`, kind: 'success' })
                            }}
                          >
                            + Déroulé
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Accordion>

            <Accordion title="Mode répétition" icon={<IconFlask color="#0ea5e9" />} description="Testez la détection de versets avant le culte.">
              <textarea
                className="settings-rehearsal-input"
                value={rehearseText}
                onChange={(e) => setRehearseText(e.target.value)}
                placeholder="Ex : ce matin nous lisons dans jean chapitre trois verset seize car dieu a tant aimé le monde…"
                rows={3}
                style={{ width: '100%', marginBottom: '12px' }}
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
                <div className="settings-result-list" style={{ marginTop: '12px' }}>
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
            </Accordion>

            {versionInfo && (
              <Accordion title="Version installée" icon={<IconInfo color="#0ea5e9" />}>
                <p className="text-sm">
                  VersePro <strong>{versionInfo.current}</strong> — Selah Studios.
                  {' '}
                  {versionInfo.update_available
                    ? <>Une version <strong>{versionInfo.latest}</strong> est disponible.</>
                    : versionInfo.checked
                      ? 'Vous êtes à jour.'
                      : 'Le contrôle des mises à jour n\'est pas activé — rien n\'est envoyé sur internet.'}
                </p>
                {versionInfo.notes && <p className="text-sm" style={{ marginTop: '8px' }}>{versionInfo.notes}</p>}
                {isTauri ? (
                  <div className="flex gap-2" style={{ marginTop: '12px' }}>
                    <button
                      type="button"
                      className="vp-btn vp-btn--sm"
                      onClick={() => checkDesktopUpdate({ silent: false })}
                      disabled={desktopUpdateStatus === 'checking'}
                    >
                      {desktopUpdateStatus === 'checking' ? 'Vérification…' : 'Rechercher une mise à jour'}
                    </button>
                    {versionInfo.update_available && (
                      <button type="button" className="vp-btn vp-btn--primary vp-btn--sm" onClick={openDesktopUpdate}>
                        Installer {versionInfo.latest}
                      </button>
                    )}
                  </div>
                ) : versionInfo.update_available && versionInfo.url ? (
                  <p className="text-sm" style={{ marginTop: '8px' }}>
                    <a href={versionInfo.url} target="_blank" rel="noreferrer">Télécharger la mise à jour</a>
                  </p>
                ) : null}
                {desktopUpdateError && isTauri && (
                  <p className="text-sm" style={{ marginTop: '8px', color: 'var(--danger)' }}>{desktopUpdateError}</p>
                )}
              </Accordion>
            )}
          </div>
        </section>



      </main>
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
