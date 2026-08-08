import React, { useState, useEffect } from 'react'
import { useStore } from '../store.js'
import { shallow } from 'zustand/shallow'
import { Icon, SkeletonRows, EmptyState } from './ui.jsx'
import { BACKEND_BASE } from '../env.js'

export default function History() {
  const {
    history,
    fetchHistory,
    sessionsList,
    activeSessionDetails,
    fetchSessions,
    fetchSessionDetails,
    generateSessionSummary,
    aiActive,
    historyLoading,
    sessionsLoading,
    addToast
  } = useStore(s => ({
    history: s.history,
    fetchHistory: s.fetchHistory,
    sessionsList: s.sessionsList,
    activeSessionDetails: s.activeSessionDetails,
    fetchSessions: s.fetchSessions,
    fetchSessionDetails: s.fetchSessionDetails,
    generateSessionSummary: s.generateSessionSummary,
    aiActive: s.aiActive,
    historyLoading: s.historyLoading,
    sessionsLoading: s.sessionsLoading,
    addToast: s.addToast
  }), shallow)

  const [activeTab, setActiveTab] = useState('verses') // 'verses' ou 'sessions'
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [summaryError, setSummaryError] = useState(null)

  useEffect(() => {
    fetchHistory()
    fetchSessions()
  }, [])

  const handleSelectSession = async (sessionId) => {
    if (selectedSessionId === sessionId) {
      setSelectedSessionId(null)
    } else {
      setSelectedSessionId(sessionId)
      await fetchSessionDetails(sessionId)
    }
  }

  const handleGenerateSummary = async (e, sessionId) => {
    e.stopPropagation()
    setLoadingSummary(true)
    setSummaryError(null)
    try {
      const result = await generateSessionSummary(sessionId)
      if (result?.error) {
        setSummaryError(result.error)
      } else {
        addToast({ message: 'Résumé du sermon généré', kind: 'success' })
      }
    } finally {
      setLoadingSummary(false)
    }
  }

  // Parseur markdown simple pour afficher le résumé proprement
  const renderSummary = (text) => {
    if (!text) return null
    return text.split('\n').map((line, index) => {
      const cleanLine = line.replace(/\*\*/g, '').replace(/\*/g, '').trim()

      if (line.startsWith('### ') || line.startsWith('#### ')) {
        return <h4 key={index} className="text-xs font-bold text-zinc-100 mt-3 mb-1.5 font-sans">{cleanLine.replace(/^#+\s+/, '')}</h4>
      }
      if (line.startsWith('## ')) {
        return <h3 key={index} className="text-sm font-bold text-purple-300 mt-4 mb-2 border-b border-white/5 pb-1 font-sans">{cleanLine.replace('## ', '')}</h3>
      }
      if (line.startsWith('# ')) {
        return <h2 key={index} className="text-base font-bold text-sky-300 mt-5 mb-3 font-sans">{cleanLine.replace('# ', '')}</h2>
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return <li key={index} className="ml-4 list-disc text-xs text-zinc-300 my-1 font-sans">{cleanLine.replace(/^[-*]\s+/, '')}</li>
      }
      if (line.trim() === '') {
        return <div key={index} className="h-2"></div>
      }
      return <p key={index} className="text-xs text-zinc-300 leading-relaxed my-1 font-sans">{cleanLine}</p>
    })
  }

  return (
    <div className="space-y-6">
      {/* En-tête avec Sélecteur d'Onglets */}
      <div className="vp-panel p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-[var(--text-main)] tracking-tight font-sans">Historique & rapports</h2>
            <p className="text-xs text-[var(--text-faint)] mt-0.5 font-sans">Retrouvez les versets détectés et les résumés de prédications générés</p>
          </div>

          <div className="flex items-center gap-3">
            {/* Onglets */}
            <div className="vp-segmented text-xs">
              <button
                onClick={() => setActiveTab('verses')}
                className={activeTab === 'verses' ? 'is-active' : ''}
              >
                Versets
              </button>
              <button
                onClick={() => setActiveTab('sessions')}
                className={activeTab === 'sessions' ? 'is-active' : ''}
              >
                Sessions
              </button>
            </div>

            <button
              onClick={() => {
                fetchHistory()
                fetchSessions()
              }}
              className="vp-btn vp-btn--ghost vp-btn--sm font-bold text-xs"
            >
              Actualiser
            </button>
          </div>
        </div>
      </div>

      {/* SECTION ONGLETS : VERSETS */}
      {activeTab === 'verses' && (
        <div className="vp-panel overflow-hidden">
          {historyLoading ? (
            <div className="p-4"><SkeletonRows rows={5} height={72} /></div>
          ) : history.length === 0 ? (
            <div className="p-6">
              <EmptyState icon="book" title="Aucun verset détecté pour le moment">
                Les versets reconnus pendant les cultes apparaîtront ici avec leur contexte.
              </EmptyState>
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-weak)]">
              {history.map((verse) => (
                <div
                  key={verse.id}
                  className="p-4 hover:bg-[var(--surface-hover)] transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-1.5">
                        <span className="live-card-badge is-local">
                          {verse.reference}
                        </span>
                        {Boolean(verse.validated_manually) && (
                          <span className="vp-chip is-ok">
                            Validé
                          </span>
                        )}
                        {Boolean(verse.sent_to_propresenter) && (
                          <span className="vp-chip is-accent">
                            Projeté
                          </span>
                        )}
                      </div>

                      <div className="text-[var(--text-faint)] text-[10px] font-sans">
                        {verse.book} {verse.chapter}:{verse.verse_start}
                        {verse.verse_end && `-${verse.verse_end}`}
                      </div>

                      {verse.context_text && (
                        <div className="mt-2 text-[var(--text-dim)] text-xs italic font-mono bg-[var(--surface-2)] p-3 rounded-xl border border-[var(--border-weak)] max-w-2xl leading-relaxed">
                          "{verse.context_text}"
                        </div>
                      )}
                    </div>

                    <div className="text-right text-[9px] text-[var(--text-faint)] font-mono">
                      <div>{new Date(verse.detected_at).toLocaleDateString('fr-FR')}</div>
                      <div className="mt-0.5">{new Date(verse.detected_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* SECTION ONGLETS : SESSIONS */}
      {activeTab === 'sessions' && (
        <div className="space-y-4">
          {sessionsLoading ? (
            <SkeletonRows rows={3} height={76} />
          ) : sessionsList.length === 0 ? (
            <div className="vp-panel p-6">
              <EmptyState icon="folder" title="Aucune session enregistrée">
                Chaque culte capté crée une session avec sa transcription et son résumé.
              </EmptyState>
            </div>
          ) : (
            sessionsList.map((session) => {
              const isSelected = selectedSessionId === session.id
              const hasSummary = !!session.summary
              const hasTranscript = !!session.transcript

              return (
                <div
                  key={session.id}
                  className={`vp-panel transition-all overflow-hidden ${
                    isSelected ? 'border-[var(--border-strong)]' : 'hover:border-[var(--border-strong)]'
                  }`}
                >
                  {/* En-tête de session */}
                  <div
                    onClick={() => handleSelectSession(session.id)}
                    className="p-5 flex items-center justify-between cursor-pointer select-none"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-[var(--accent-soft)] border border-[var(--border-strong)] flex items-center justify-center text-[var(--accent)] font-bold text-sm">
                        {session.id}
                      </div>
                      <div>
                        <h3 className="font-bold text-[var(--text-main)] text-sm font-sans">{session.name}</h3>
                        <p className="text-[10px] text-[var(--text-faint)] mt-0.5 font-sans">
                          Démarrée le {new Date(session.started_at).toLocaleDateString('fr-FR')} à {new Date(session.started_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                          {session.ended_at && ` • Terminée (durée : ${session.duration_minutes || '?'} min)`}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="px-2.5 py-1 bg-[var(--surface-2)] text-[var(--text-main)] border border-[var(--border-weak)] rounded-lg text-[10px] font-semibold font-sans">
                        {session.verse_count || 0} verset(s)
                      </span>

                      {hasSummary ? (
                        <>
                          <span className="vp-chip is-ok flex items-center gap-1">
                            Résumé IA prêt
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              window.open(`${BACKEND_BASE}/api/v1/history/sessions/${session.id}/export-recap.pptx`, '_blank')
                            }}
                            className="vp-btn vp-btn--sm flex items-center gap-1"
                            title="Exporter les slides de synthèse hors ligne"
                          >
                            Slides IA
                          </button>
                        </>
                      ) : (
                        aiActive && hasTranscript && (
                          <button
                            onClick={(e) => handleGenerateSummary(e, session.id)}
                            disabled={loadingSummary}
                            className="vp-btn vp-btn--primary vp-btn--sm flex items-center gap-1 disabled:opacity-50"
                          >
                            {loadingSummary ? 'Génération…' : 'Générer le résumé'}
                          </button>
                        )
                      )}

                      <span className="text-[var(--text-faint)] text-xs">
                        {isSelected ? '▲' : '▼'}
                      </span>
                    </div>
                  </div>

                  {/* Détail extensible de la session */}
                  {isSelected && activeSessionDetails && activeSessionDetails.id === session.id && (
                    <div className="border-t border-[var(--border-weak)] bg-[var(--surface-2)] p-6 space-y-6">
                      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                        {/* Colonne Transcription cumulée */}
                        <div className="lg:col-span-7 space-y-3">
                          <h4 className="text-[9px] font-bold uppercase tracking-widest text-[var(--text-faint)] font-mono">
                            Transcription cumulée du sermon
                          </h4>
                          <div className="p-4 bg-[var(--surface-0)] border border-[var(--border-weak)] rounded-2xl text-xs text-[var(--text-main)] font-mono leading-relaxed max-h-[380px] overflow-y-auto">
                            {activeSessionDetails.transcript ? (
                              activeSessionDetails.transcript
                            ) : (
                              <span className="text-[var(--text-faint)] italic">Aucune transcription enregistrée pour cette session.</span>
                            )}
                          </div>
                        </div>

                        {/* Colonne Résumé IA */}
                        <div className="lg:col-span-5 space-y-3">
                          <h4 className="text-[9px] font-bold uppercase tracking-widest text-[var(--vp-ai)] font-mono flex items-center gap-1">
                            Résumé IA
                          </h4>
                          {summaryError && (
                            <p className="text-[10px] text-[var(--color-danger-ink)] font-sans bg-[var(--danger-soft)] border border-[var(--border-strong)] rounded-lg px-3 py-2">
                              {summaryError}
                            </p>
                          )}
                          <div className="p-5 bg-[var(--vp-ai-soft)] border border-[var(--border-strong)] rounded-2xl max-h-[380px] overflow-y-auto">
                            {activeSessionDetails.summary ? (
                              <div className="space-y-2">
                                {renderSummary(activeSessionDetails.summary)}
                              </div>
                            ) : (
                              <div className="text-center py-8 text-[var(--text-faint)]">
                                <p className="text-xs">Aucun résumé généré.</p>
                                {aiActive && activeSessionDetails.transcript ? (
                                  <button
                                    onClick={(e) => handleGenerateSummary(e, session.id)}
                                    disabled={loadingSummary}
                                    className="mt-3 vp-btn vp-btn--primary vp-btn--sm inline-flex items-center gap-1 disabled:opacity-50"
                                  >
                                    {loadingSummary ? 'Génération…' : 'Générer maintenant'}
                                  </button>
                                ) : (
                                  <p className="text-[10px] mt-1.5 text-[var(--color-danger-ink)] font-sans">
                                    {!aiActive ? "Activez l'agent IA (clé API requise)" : "La transcription est vide."}
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      )}

      {/* Stats rapides */}
      {activeTab === 'verses' && history.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="vp-panel p-4 text-center">
            <div className="text-3xl font-bold text-[var(--accent)] font-sans">{history.length}</div>
            <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Total detected verses</div>
          </div>
          <div className="vp-panel p-4 text-center">
            <div className="text-3xl font-bold text-[var(--success)] font-sans">
              {history.filter(v => v.sent_to_propresenter).length}
            </div>
            <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Projected verses</div>
          </div>
          <div className="vp-panel p-4 text-center">
            <div className="text-3xl font-bold text-[var(--vp-ai)] font-sans">
              {new Set(history.map(v => v.reference)).size}
            </div>
            <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Unique scripture references</div>
          </div>
        </div>
      )}
    </div>
  )
}
