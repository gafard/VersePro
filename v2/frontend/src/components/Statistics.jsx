import React, { useEffect } from 'react'
import { useStore } from '../store.js'
import { SkeletonRows, Skeleton } from './ui.jsx'

export default function Statistics() {
  const { statistics, fetchStatistics, statsLoading } = useStore()
  
  useEffect(() => {
    fetchStatistics(30)
  }, [])
  
  if (statsLoading || !statistics) {
    return (
      <div className="space-y-6">
        <div className="glass-copilot p-6"><Skeleton width={220} height={20} /><Skeleton width={330} height={12} style={{ marginTop: 10 }} /></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="glass-copilot p-5"><Skeleton width={64} height={30} /><Skeleton width={110} height={10} style={{ marginTop: 10 }} /></div>)}
        </div>
        <div className="glass-copilot p-6"><SkeletonRows rows={5} height={30} /></div>
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="glass-copilot p-6">
        <h2 className="text-xl font-bold text-zinc-100 tracking-tight font-sans">Analyse d'activité</h2>
        <p className="text-xs text-zinc-400 mt-0.5 font-sans">Vue d'ensemble des 30 derniers jours de détections</p>
      </div>
      
      {/* Stats principales */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-indigo-400 font-sans">{statistics.total_verses}</div>
          <div className="text-[10px] text-zinc-400 mt-1 uppercase tracking-widest font-mono">Versets détectés</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-emerald-400 font-sans">{statistics.unique_references}</div>
          <div className="text-[10px] text-zinc-400 mt-1 uppercase tracking-widest font-mono">Versets uniques</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-purple-400 font-sans">{statistics.total_sessions}</div>
          <div className="text-[10px] text-zinc-400 mt-1 uppercase tracking-widest font-mono">Sessions enregistrées</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-cyan-400 font-sans">
            {statistics.avg_verses_per_session?.toFixed(1) || 0}
          </div>
          <div className="text-[10px] text-zinc-400 mt-1 uppercase tracking-widest font-mono">Versets / session</div>
        </div>
      </div>
      
      {/* Top Livres & Top Versets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Livres */}
        <div className="glass-copilot p-6">
          <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider mb-5">Livres les plus cités</h3>
          
          {statistics.top_books && statistics.top_books.length > 0 ? (
            <div className="space-y-4">
              {statistics.top_books.map((book, index) => (
                <div key={book.book} className="flex items-center">
                  <div className="w-7 h-7 bg-indigo-500/10 border border-indigo-500/30 rounded-full flex items-center justify-center font-bold text-indigo-300 mr-3 text-xs">
                    {index + 1}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-zinc-200">{book.book}</div>
                    <div className="w-full bg-white/[0.06] rounded-full h-1 mt-1.5 overflow-hidden">
                      <div
                        className="bg-indigo-500/100 h-full rounded-full"
                        style={{ width: `${(book.count / statistics.top_books[0].count) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="ml-4 font-bold text-xs text-zinc-400">{book.count}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-zinc-600 text-center py-6 text-xs">Aucune donnée disponible</div>
          )}
        </div>
        
        {/* Top Versets */}
        <div className="glass-copilot p-6">
          <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider mb-5">Versets les plus cités</h3>
          
          {statistics.top_verses && statistics.top_verses.length > 0 ? (
            <div className="space-y-2.5">
              {statistics.top_verses.map((verse, index) => (
                <div
                  key={verse.reference}
                  className="flex items-center justify-between p-3 bg-white/[0.04] border border-white/5 rounded-2xl"
                >
                  <div className="flex items-center space-x-3">
                    <div className="w-6 h-6 bg-purple-500/10 border border-purple-500/30 rounded-full flex items-center justify-center text-[10px] font-bold text-purple-300">
                      {index + 1}
                    </div>
                    <span className="font-semibold text-zinc-200 text-xs">{verse.reference}</span>
                  </div>
                  <span className="px-2.5 py-1 bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 rounded-lg text-[10px] font-bold">
                    {verse.count}x
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-zinc-600 text-center py-6 text-xs">Aucune donnée disponible</div>
          )}
        </div>
      </div>
      
      {/* Versets par jour */}
      <div className="glass-copilot p-6">
        <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider mb-6">Activité quotidienne</h3>
        
        {statistics.verses_per_day && statistics.verses_per_day.length > 0 ? (
          <div className="h-44 flex items-end space-x-2 pt-6 px-2 border-b border-white/5">
            {statistics.verses_per_day.map((day) => {
              const maxCount = Math.max(...statistics.verses_per_day.map(d => d.count))
              const height = (day.count / (maxCount || 1)) * 100
              
              return (
                <div
                  key={day.date}
                  className="flex-1 flex flex-col items-center group relative"
                >
                  <div className="absolute bottom-full mb-2 bg-zinc-800 text-white text-[9px] font-bold px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap shadow-lg">
                    {day.count} versets
                  </div>
                  
                  <div
                    className="w-full bg-indigo-500/20 group-hover:bg-indigo-500/100 rounded-t transition-all duration-200"
                    style={{ height: `${height}%`, minHeight: day.count > 0 ? '5px' : '1px' }}
                  />
                  <div className="text-[8px] text-zinc-500 mt-2 font-mono whitespace-nowrap overflow-hidden text-ellipsis max-w-[35px] tracking-tighter">
                    {new Date(day.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-zinc-600 text-center py-8 text-xs">Aucune activité trouvée</div>
        )}
      </div>
    </div>
  )
}
