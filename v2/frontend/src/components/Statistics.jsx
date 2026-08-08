import React, { useEffect } from 'react'
import { useStore } from '../store.js'
import { SkeletonRows, Skeleton } from './ui.jsx'

export default function Statistics() {
  const statistics = useStore(s => s.statistics)
  const fetchStatistics = useStore(s => s.fetchStatistics)
  const statsLoading = useStore(s => s.statsLoading)
  
  useEffect(() => {
    fetchStatistics(30)
  }, [])
  
  if (statsLoading || !statistics) {
    return (
      <div className="space-y-6">
        <div className="vp-panel p-6"><Skeleton width={220} height={20} /><Skeleton width={330} height={12} style={{ marginTop: 10 }} /></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="vp-panel p-5"><Skeleton width={64} height={30} /><Skeleton width={110} height={10} style={{ marginTop: 10 }} /></div>)}
        </div>
        <div className="vp-panel p-6"><SkeletonRows rows={5} height={30} /></div>
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="vp-panel p-6">
        <h2 className="text-xl font-bold text-[var(--text-main)] tracking-tight font-sans">Analyse d'activité</h2>
        <p className="text-xs text-[var(--text-faint)] mt-0.5 font-sans">Vue d'ensemble des 30 derniers jours de détections</p>
      </div>
      
      {/* Stats principales */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="vp-panel p-5">
          <div className="text-3xl font-bold text-[var(--accent)] font-sans">{statistics.total_verses}</div>
          <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Versets détectés</div>
        </div>
        
        <div className="vp-panel p-5">
          <div className="text-3xl font-bold text-[var(--success)] font-sans">{statistics.unique_references}</div>
          <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Versets uniques</div>
        </div>
        
        <div className="vp-panel p-5">
          <div className="text-3xl font-bold text-[var(--vp-ai)] font-sans">{statistics.total_sessions}</div>
          <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Sessions enregistrées</div>
        </div>
        
        <div className="vp-panel p-5">
          <div className="text-3xl font-bold text-[var(--warning)] font-sans">
            {statistics.avg_verses_per_session?.toFixed(1) || 0}
          </div>
          <div className="text-[10px] text-[var(--text-faint)] mt-1 uppercase tracking-widest font-mono">Versets / session</div>
        </div>
      </div>
      
      {/* Top Livres & Top Versets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Livres */}
        <div className="vp-panel p-6">
          <h3 className="text-sm font-bold text-[var(--text-faint)] uppercase tracking-wider mb-5">Livres les plus cités</h3>
          
          {statistics.top_books && statistics.top_books.length > 0 ? (
            <div className="space-y-4">
               {statistics.top_books.map((book, index) => (
                <div key={book.book} className="flex items-center">
                  <div className="w-7 h-7 bg-[var(--accent-soft)] border border-[var(--border-strong)] rounded-full flex items-center justify-center font-bold text-[var(--accent)] mr-3 text-xs">
                    {index + 1}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-[var(--text-dim)]">{book.book}</div>
                    <div className="w-full bg-[var(--surface-2)] rounded-full h-1 mt-1.5 overflow-hidden">
                      <div
                        className="bg-[var(--accent)] h-full rounded-full"
                        style={{ width: `${(book.count / statistics.top_books[0].count) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="ml-4 font-bold text-xs text-[var(--text-faint)]">{book.count}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[var(--text-faint)] text-center py-6 text-xs font-sans">Aucune donnée disponible</div>
          )}
        </div>
        
        {/* Top Versets */}
        <div className="vp-panel p-6">
          <h3 className="text-sm font-bold text-[var(--text-faint)] uppercase tracking-wider mb-5">Versets les plus cités</h3>
          
          {statistics.top_verses && statistics.top_verses.length > 0 ? (
            <div className="space-y-2.5">
              {statistics.top_verses.map((verse, index) => (
                <div
                  key={verse.reference}
                  className="flex items-center justify-between p-3 bg-[var(--surface-2)] border border-[var(--border-weak)] rounded-2xl"
                >
                  <div className="flex items-center space-x-3">
                    <div className="w-6 h-6 bg-[var(--accent-soft)] border border-[var(--border-strong)] rounded-full flex items-center justify-center text-[10px] font-bold text-[var(--accent)]">
                      {index + 1}
                    </div>
                    <span className="font-semibold text-[var(--text-dim)] text-xs">{verse.reference}</span>
                  </div>
                  <span className="px-2.5 py-1 bg-[var(--accent-soft)] border border-[var(--border-strong)] text-[var(--accent)] rounded-lg text-[10px] font-bold">
                    {verse.count}x
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[var(--text-faint)] text-center py-6 text-xs font-sans">Aucune donnée disponible</div>
          )}
        </div>
      </div>
      
      {/* Versets par jour */}
      <div className="vp-panel p-6">
        <h3 className="text-sm font-bold text-[var(--text-faint)] uppercase tracking-wider mb-6">Activité quotidienne</h3>
        
        {statistics.verses_per_day && statistics.verses_per_day.length > 0 ? (
          <div className="h-44 flex items-end space-x-2 pt-6 px-2 border-b border-[var(--border-weak)]">
            {statistics.verses_per_day.map((day) => {
              const maxCount = Math.max(...statistics.verses_per_day.map(d => d.count))
              const height = (day.count / (maxCount || 1)) * 100
              
              return (
                <div
                  key={day.date}
                  className="flex-1 flex flex-col items-center group relative"
                >
                  <div className="absolute bottom-full mb-2 bg-[var(--surface-2)] text-[var(--text-main)] border border-[var(--border-strong)] text-[9px] font-bold px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap shadow-lg">
                    {day.count} versets
                  </div>
                  
                  <div
                    className="w-full bg-[var(--accent-soft)] group-hover:bg-[var(--accent)] rounded-t transition-all duration-200"
                    style={{ height: `${height}%`, minHeight: day.count > 0 ? '5px' : '1px' }}
                  />
                  <div className="text-[8px] text-[var(--text-faint)] mt-2 font-mono whitespace-nowrap overflow-hidden text-ellipsis max-w-[35px] tracking-tighter">
                    {new Date(day.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-[var(--text-faint)] text-center py-8 text-xs font-sans">Aucune activité trouvée</div>
        )}
      </div>
    </div>
  )
}
