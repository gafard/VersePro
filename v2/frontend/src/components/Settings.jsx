import React, { useEffect, useMemo, useState } from 'react'
import { useStore } from '../store.js'

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
    addToast
  } = useStore()

  const [form, setForm] = useState({
    auto_send: false,
    bible_version: activeBible || 'LSG',
    propresenter_host: '127.0.0.1',
    propresenter_port: 12345,
    deepgram_model: 'nova-2',
    deepgram_language: 'fr',
    ai_agent_enabled: true,
    ai_confidence_threshold: 95,
    ai_filtering_mode: 'strict'
  })
  const [secretForm, setSecretForm] = useState({
    deepgram_api_key: '',
    openrouter_api_key: '',
    gemini_api_key: ''
  })
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)
  const [helpModal, setHelpModal] = useState(null)

  useEffect(() => {
    fetchBibles()
    fetchSettings()
  }, [])

  useEffect(() => {
    if (!settings) return
    setForm({
      auto_send: Boolean(settings.auto_send),
      bible_version: settings.bible_version || activeBible || 'LSG',
      propresenter_host: settings.propresenter_host || '127.0.0.1',
      propresenter_port: settings.propresenter_port || 12345,
      deepgram_model: settings.deepgram_model || 'nova-2',
      deepgram_language: settings.deepgram_language || 'fr',
      ai_agent_enabled: Boolean(settings.ai_agent_enabled),
      ai_confidence_threshold: settings.ai_confidence_threshold || 95,
      ai_filtering_mode: settings.ai_filtering_mode || 'strict'
    })
  }, [settings, activeBible])

  const statusCards = useMemo(() => ([
    {
      label: 'Serveur',
      value: settings ? 'Connecte' : 'Lecture',
      tone: 'good'
    },
    {
      label: 'ProPresenter',
      value: propresenterConnected ? 'Pret' : 'Manuel',
      tone: propresenterConnected ? 'good' : 'warn'
    },
    {
      label: 'IA',
      value: aiActive ? 'Active' : 'Inactive',
      tone: aiActive ? 'good' : 'neutral'
    }
  ]), [settings, propresenterConnected, aiActive])

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const updateSecret = (field, value) => {
    setSecretForm((current) => ({ ...current, [field]: value }))
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
        propresenter_port: Number(form.propresenter_port) || 12345,
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

  return (
    <div className="settings-page app-soft-page">
      <section className="settings-hero">
        <div>
          <span>Parametres</span>
          <h1>Console de configuration</h1>
          <p>
            Les reglages critiques restent lisibles, calmes et modifiables sans toucher aux fichiers systeme.
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

      <section className="settings-grid">
        <div className="settings-card is-wide">
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
            Active uniquement la projection directe des references explicites et tres fiables.
            Les deductions IA restent en validation manuelle.
          </p>
        </div>

        <label className="settings-card">
          <span>Bible</span>
          <h2>Version par defaut</h2>
          <select value={form.bible_version} onChange={(e) => updateField('bible_version', e.target.value)}>
            {availableBibles.map((code) => (
              <option key={code} value={code}>
                {code} - {BIBLE_NAMES[code] || code}
              </option>
            ))}
          </select>
        </label>

        <div className="settings-card">
          <span>ProPresenter</span>
          <h2>Connexion locale</h2>
          <div className="settings-two-cols">
            <label>
              <small>Hote</small>
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
        </div>

        <div className="settings-card">
          <span>Deepgram</span>
          <h2>Transcription cloud</h2>
          <div className="settings-two-cols">
            <label>
              <small>Modele</small>
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
                <option value="fr">Francais</option>
                <option value="en">Anglais</option>
                <option value="es">Espagnol</option>
                <option value="pt">Portugais</option>
              </select>
            </label>
          </div>
          <div style={{ marginTop: '12px' }}>
            <label>
              <small style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <span>Cle API Deepgram</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('deepgram')}
                  style={{ background: 'none', border: 'none', color: 'var(--vp-accent)', cursor: 'pointer', fontSize: '11px', padding: 0, fontWeight: 'normal' }}
                >
                  Obtenir une clé gratuite
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

        <div className="settings-card is-wide">
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
          <p style={{ marginBottom: '16px' }}>
            L IA peut proposer une reference quand le predicteur paraphrase, mais elle ne doit pas prendre le controle de l ecran.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <label>
              <small style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <span>Cle API OpenRouter</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('openrouter')}
                  style={{ background: 'none', border: 'none', color: 'var(--vp-accent)', cursor: 'pointer', fontSize: '10px', padding: 0, fontWeight: 'normal' }}
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
              <small style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <span>Cle API Gemini Direct</span>
                <button
                  type="button"
                  onClick={() => setHelpModal('gemini')}
                  style={{ background: 'none', border: 'none', color: 'var(--vp-accent)', cursor: 'pointer', fontSize: '10px', padding: 0, fontWeight: 'normal' }}
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

          <div style={{ marginTop: '16px', borderTop: '1px solid var(--vp-border)', paddingTop: '16px' }}>
            <label style={{ display: 'block' }}>
              <small>Tamis sémantique (Sensibilité d'écoute IA)</small>
              <div className="live-segmented" style={{ width: 'fit-content', marginTop: '8px' }}>
                <button
                  type="button"
                  className={form.ai_filtering_mode === 'strict' ? 'is-active' : ''}
                  onClick={() => updateField('ai_filtering_mode', 'strict')}
                  style={{ border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 'bold' }}
                >
                  Strict — filtre par mots-clés
                </button>
                <button
                  type="button"
                  className={form.ai_filtering_mode === 'open' ? 'is-active' : ''}
                  onClick={() => updateField('ai_filtering_mode', 'open')}
                  style={{ border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 'bold' }}
                >
                  Ouvert — analyse tout
                </button>
              </div>
              <span style={{ fontSize: '11px', color: 'var(--vp-text-dim)', display: 'block', marginTop: '6px' }}>
                Le <strong>Mode Strict</strong> filtre les phrases d'après une liste de mots-clés théologiques pour économiser les performances. Le <strong>Mode Ouvert</strong> analyse tout (recommandé pour capturer des récits ou des phrases implicites comme "il a marché sur l'eau").
              </span>
            </label>
          </div>

          <div style={{ marginTop: '16px', borderTop: '1px solid var(--vp-border)', paddingTop: '16px' }}>
            <label>
              <small>
                Seuil de confiance minimal (IA) : <strong>{form.ai_confidence_threshold}%</strong>
                {form.ai_confidence_threshold >= 90 && (
                  <span style={{ color: 'var(--vp-warn)', fontSize: '11px', display: 'block', marginTop: '2px', fontWeight: 'normal' }}>
                    Seuil élevé : l'IA rejettera silencieusement de nombreuses suggestions pour proteger le direct.
                  </span>
                )}
              </small>
              <input
                type="range"
                min="50"
                max="99"
                value={form.ai_confidence_threshold}
                onChange={(e) => updateField('ai_confidence_threshold', Number(e.target.value))}
                style={{ width: '100%', marginTop: '8px' }}
              />
              <span style={{ fontSize: '11px', color: 'var(--vp-text-dim)', display: 'block', marginTop: '4px' }}>
                Toute suggestion IA sous ce seuil sera automatiquement rejetee pour eviter les hallucinations.
              </span>
            </label>
          </div>
        </div>
      </section>

      <div className="settings-footer">
        <div>
          <strong>{savedAt ? 'Parametres sauvegardes' : 'Pret a sauvegarder'}</strong>
          <span>{savedAt ? savedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : 'Les changements seront appliques au backend.'}</span>
        </div>
        <button onClick={save} disabled={saving}>
          {saving ? 'Sauvegarde...' : 'Sauvegarder'}
        </button>
      </div>

      {helpModal && (
        <div className="vp-modal-backdrop">
          <div className="vp-modal" style={{ maxWidth: '500px' }}>
            <h3 style={{ marginBottom: '12px' }}>
              {helpModal === 'deepgram' && 'Obtenir une clé API Deepgram'}
              {helpModal === 'openrouter' && 'Obtenir une clé API OpenRouter'}
              {helpModal === 'gemini' && 'Obtenir une clé API Gemini Direct'}
            </h3>
            
            <div style={{ fontSize: '13px', lineHeight: '1.6' }}>
              {helpModal === 'deepgram' && (
                <ol style={{ paddingLeft: '16px', listStyleType: 'decimal' }}>
                  <li style={{ marginBottom: '6px' }}>Allez sur le site <strong><a href="https://console.deepgram.com" target="_blank" rel="noreferrer" >console.deepgram.com</a></strong> et créez un compte gratuit.</li>
                  <li style={{ marginBottom: '6px' }}>Deepgram vous offre <strong>200 $ de crédits gratuits</strong> au démarrage (ce qui équivaut à plus de 10 000 heures de transcription).</li>
                  <li style={{ marginBottom: '6px' }}>Cliquez sur <strong>"API Keys"</strong> dans la barre latérale gauche, puis sur <strong>"Create New API Key"</strong>.</li>
                  <li style={{ marginBottom: '6px' }}>Sélectionnez le rôle d'administrateur ou d'écriture, nommez la clé "VersePro", puis cliquez sur créer.</li>
                  <li style={{ marginBottom: '6px' }}>Copiez la clé générée (elle commence par <code>dg_</code>) et collez-la dans le champ correspondant dans VersePro.</li>
                </ol>
              )}
              {helpModal === 'openrouter' && (
                <ol style={{ paddingLeft: '16px', listStyleType: 'decimal' }}>
                  <li style={{ marginBottom: '6px' }}>Allez sur <strong><a href="https://openrouter.ai" target="_blank" rel="noreferrer" >openrouter.ai</a></strong> et inscrivez-vous.</li>
                  <li style={{ marginBottom: '6px' }}>Dans votre compte, allez dans la section <strong>"Keys"</strong> (ou Clés API).</li>
                  <li style={{ marginBottom: '6px' }}>Créez une nouvelle clé API et nommez-la "VersePro".</li>
                  <li style={{ marginBottom: '6px' }}>Copiez la clé (elle commence par <code>sk-or-v1-</code>). Elle vous donne accès à de nombreux modèles d'IA, y compris certains gratuits (comme Gemini Flash).</li>
                </ol>
              )}
              {helpModal === 'gemini' && (
                <ol style={{ paddingLeft: '16px', listStyleType: 'decimal' }}>
                  <li style={{ marginBottom: '6px' }}>Allez sur <strong><a href="https://aistudio.google.com" target="_blank" rel="noreferrer" >aistudio.google.com</a></strong> avec votre compte Google.</li>
                  <li style={{ marginBottom: '6px' }}>Cliquez sur <strong>"Get API Key"</strong> en haut à gauche.</li>
                  <li style={{ marginBottom: '6px' }}>Créez une clé dans un nouveau projet ou un projet existant.</li>
                  <li style={{ marginBottom: '6px' }}>Copiez la clé générée (elle commence par <code>AIzaSy</code>) et collez-la dans VersePro. C'est 100% gratuit dans la limite des quotas standards d'AI Studio.</li>
                </ol>
              )}
            </div>
            
            <button
              onClick={() => setHelpModal(null)}
              className="vp-btn vp-btn--primary"
              style={{ marginTop: '20px', width: '100%' }}
            >
              Compris, fermer
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
