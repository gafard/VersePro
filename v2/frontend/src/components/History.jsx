import React, { useState, useEffect } from 'react'
import { useStore } from '../store.js'

export default function History() {
  const { 
    history, 
    fetchHistory,
    sessionsList,
    activeSessionDetails,
    fetchSessions,
    fetchSessionDetails,
    generateSessionSummary,
    aiActive
  } = useStore()
  
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
        return <h4 key={index} className="text-xs font-bold text-slate-800 mt-3 mb-1.5 font-sans">{cleanLine.replace(/^#+\s+/, '')}</h4>
      }
      if (line.startsWith('## ')) {
        return <h3 key={index} className="text-sm font-bold text-purple-700 mt-4 mb-2 border-b border-slate-100 pb-1 font-sans">{cleanLine.replace('## ', '')}</h3>
      }
      if (line.startsWith('# ')) {
        return <h2 key={index} className="text-base font-bold text-sky-700 mt-5 mb-3 font-sans">{cleanLine.replace('# ', '')}</h2>
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return <li key={index} className="ml-4 list-disc text-xs text-slate-600 my-1 font-sans">{cleanLine.replace(/^[-*]\s+/, '')}</li>
      }
      if (line.trim() === '') {
        return <div key={index} className="h-2"></div>
      }
      return <p key={index} className="text-xs text-slate-600 leading-relaxed my-1 font-sans">{cleanLine}</p>
    })
  }
 
  return (
    <div className="space-y-6">
      {/* En-tête avec Sélecteur d'Onglets */}
      <div className="glass-copilot p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-800 tracking-tight font-sans">History & Reports</h2>
            <p className="text-xs text-slate-500 mt-0.5 font-sans">Review past scripture detections and generated sermon summaries</p>
          </div>
          
          <div className="flex items-center gap-3">
            {/* Onglets */}
            <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs">
              <button
                onClick={() => setActiveTab('verses')}
                className={`px-4 py-1.5 rounded-lg font-medium transition-all duration-200 ${
                  activeTab === 'verses'
                    ? 'bg-white text-slate-800 shadow-sm border border-slate-200'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                📖 Verses
              </button>
              <button
                onClick={() => setActiveTab('sessions')}
                className={`px-4 py-1.5 rounded-lg font-medium transition-all duration-200 ${
                  activeTab === 'sessions'
                    ? 'bg-white text-slate-800 shadow-sm border border-slate-200'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                📁 Sessions
              </button>
            </div>
 
            <button
              onClick={() => {
                fetchHistory()
                fetchSessions()
              }}
              className="px-4 py-1.5 bg-slate-100 border border-slate-200 text-slate-700 rounded-xl hover:bg-slate-200 font-bold text-xs transition-all"
            >
              🔄 Refresh
            </button>
          </div>
        </div>
      </div>
      
      {/* SECTION ONGLETS : VERSETS */}
      {activeTab === 'verses' && (
        <div className="glass-copilot overflow-hidden">
          {history.length === 0 ? (
            <div className="text-center py-12 text-slate-300">
              <div className="text-5xl mb-4">📚</div>
              <p className="text-xs">No verses in history yet</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {history.map((verse) => (
                <div
                  key={verse.id}
                  className="p-4 hover:bg-slate-50/50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-1.5">
                        <span className="px-3 py-1 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-full text-[10px] font-bold uppercase tracking-wider">
                          {verse.reference}
                        </span>
                        {verse.validated_manually && (
                          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-100 rounded text-[9px] font-semibold">
                            ✓ Validated
                          </span>
                        )}
                        {verse.sent_to_propresenter && (
                          <span className="px-2 py-0.5 bg-sky-50 text-sky-700 border border-sky-100 rounded text-[9px] font-semibold">
                            📺 Projected
                          </span>
                        )}
                      </div>
                      
                      <div className="text-slate-500 text-[10px] font-sans">
                        {verse.book} {verse.chapter}:{verse.verse_start}
                        {verse.verse_end && `-${verse.verse_end}`}
                      </div>
                      
                      {verse.context_text && (
                        <div className="mt-2 text-slate-600 text-xs italic font-mono bg-slate-100/50 p-3 rounded-xl border border-slate-200/50 max-w-2xl leading-relaxed">
                          "{verse.context_text}"
                        </div>
                      )}
                    </div>
                    
                    <div className="text-right text-[9px] text-slate-400 font-mono">
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
          {sessionsList.length === 0 ? (
            <div className="glass-copilot text-center py-12 text-slate-300">
              <div className="text-5xl mb-4">📁</div>
              <p className="text-xs">No recorded sessions</p>
            </div>
          ) : (
            sessionsList.map((session) => {
              const isSelected = selectedSessionId === session.id
              const hasSummary = !!session.summary
              const hasTranscript = !!session.transcript
              
              return (
                <div 
                  key={session.id}
                  className={`glass-copilot transition-all overflow-hidden ${
                    isSelected ? 'border-slate-300' : 'hover:border-slate-300'
                  }`}
                >
                  {/* En-tête de session */}
                  <div 
                    onClick={() => handleSelectSession(session.id)}
                    className="p-5 flex items-center justify-between cursor-pointer select-none"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-sm">
                        {session.id}
                      </div>
                      <div>
                        <h3 className="font-bold text-slate-800 text-sm font-sans">{session.name}</h3>
                        <p className="text-[10px] text-slate-500 mt-0.5 font-sans">
                          Started on {new Date(session.started_at).toLocaleDateString('fr-FR')} at {new Date(session.started_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                          {session.ended_at && ` • Ended (Duration: ${session.duration_minutes || '?'} min)`}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-3">
                      <span className="px-2.5 py-1 bg-slate-100 text-slate-700 border border-slate-200 rounded-lg text-[10px] font-semibold font-sans">
                        📖 {session.verse_count || 0} verse(s)
                      </span>
                      
                      {hasSummary ? (
                        <span className="px-2.5 py-1 bg-purple-50 text-purple-700 border border-purple-100 rounded-lg text-[10px] font-semibold font-sans flex items-center gap-1">
                          🤖 AI Summary Ready
                        </span>
                      ) : (
                        aiActive && hasTranscript && (
                          <button
                            onClick={(e) => handleGenerateSummary(e, session.id)}
                            disabled={loadingSummary}
                            className="px-3 py-1 bg-purple-100 hover:bg-purple-200 text-purple-800 hover:text-purple-900 border border-purple-200 rounded-lg text-[10px] font-bold transition-all shadow-sm flex items-center gap-1 disabled:opacity-50"
                          >
                            {loadingSummary ? '⏳ Generating...' : '🤖 Generate Summary'}
                          </button>
                        )
                      )}
                      
                      <span className="text-slate-400 text-xs">
                        {isSelected ? '▲' : '▼'}
                      </span>
                    </div>
                  </div>
                  
                  {/* Détail extensible de la session */}
                  {isSelected && activeSessionDetails && activeSessionDetails.id === session.id && (
                    <div className="border-t border-slate-200 bg-slate-50/50 p-6 space-y-6">
                      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                        {/* Colonne Transcription cumulée */}
                        <div className="lg:col-span-7 space-y-3">
                          <h4 className="text-[9px] font-bold uppercase tracking-widest text-slate-500 font-mono">
                            🎙️ Cumulative Sermon Transcript
                          </h4>
                          <div className="p-4 bg-slate-100/30 border border-slate-200 rounded-2xl text-xs text-slate-700 font-mono leading-relaxed max-h-[380px] overflow-y-auto">
                            {activeSessionDetails.transcript ? (
                              activeSessionDetails.transcript
                            ) : (
                              <span className="text-slate-400 italic">No transcript logs recorded for this session.</span>
                            )}
                          </div>
                        </div>
                        
                        {/* Colonne Résumé IA */}
                        <div className="lg:col-span-5 space-y-3">
                          <h4 className="text-[9px] font-bold uppercase tracking-widest text-purple-700 font-mono flex items-center gap-1">
                            🤖 AI Summary Report
                          </h4>
                          {summaryError && (
                            <p className="text-[10px] text-red-600 font-sans bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                              ⚠️ {summaryError}
                            </p>
                          )}
                          <div className="p-5 bg-purple-50/50 border border-purple-100 rounded-2xl max-h-[380px] overflow-y-auto">
                            {activeSessionDetails.summary ? (
                              <div className="space-y-2">
                                {renderSummary(activeSessionDetails.summary)}
                              </div>
                            ) : (
                              <div className="text-center py-8 text-slate-400">
                                <p className="text-xs">No summary generated.</p>
                                {aiActive && activeSessionDetails.transcript ? (
                                  <button
                                    onClick={(e) => handleGenerateSummary(e, session.id)}
                                    disabled={loadingSummary}
                                    className="mt-3 px-4 py-2 bg-purple-100 hover:bg-purple-200 text-purple-800 border border-purple-200 rounded-xl text-[10px] font-bold transition-all shadow-sm inline-flex items-center gap-1 disabled:opacity-50"
                                  >
                                    {loadingSummary ? '⏳ Generating...' : '🤖 Generate now'}
                                  </button>
                                ) : (
                                  <p className="text-[10px] mt-1.5 text-red-500 font-sans">
                                    {!aiActive ? "Activate AI Agent (requires API Key)" : "Transcript is empty."}
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
          <div className="glass-copilot p-4 text-center">
            <div className="text-3xl font-bold text-indigo-600 font-sans">{history.length}</div>
            <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Total detected verses</div>
          </div>
          <div className="glass-copilot p-4 text-center">
            <div className="text-3xl font-bold text-emerald-600 font-sans">
              {history.filter(v => v.sent_to_propresenter).length}
            </div>
            <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Projected verses</div>
          </div>
          <div className="glass-copilot p-4 text-center">
            <div className="text-3xl font-bold text-purple-600 font-sans">
              {new Set(history.map(v => v.reference)).size}
            </div>
            <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Unique scripture references</div>
          </div>
        </div>
      )}
    </div>
  )
}
