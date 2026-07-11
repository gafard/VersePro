import React, { useEffect } from 'react'
import { useStore } from '../store.js'

export default function Statistics() {
  const { statistics, fetchStatistics } = useStore()
  
  useEffect(() => {
    fetchStatistics(30)
  }, [])
  
  if (!statistics) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400 animate-pulse text-xs font-mono">Loading statistics data...</div>
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="glass-copilot p-6">
        <h2 className="text-xl font-bold text-slate-800 tracking-tight font-sans">Activity Analytics</h2>
        <p className="text-xs text-slate-500 mt-0.5 font-sans">Overview of the last 30 days of sermon scripture detections</p>
      </div>
      
      {/* Stats principales */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-indigo-600 font-sans">{statistics.total_verses}</div>
          <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Total Verses</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-emerald-600 font-sans">{statistics.unique_references}</div>
          <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Unique Verses</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-purple-600 font-sans">{statistics.total_sessions}</div>
          <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Recorded Sessions</div>
        </div>
        
        <div className="glass-copilot p-5">
          <div className="text-3xl font-bold text-cyan-600 font-sans">
            {statistics.avg_verses_per_session?.toFixed(1) || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-mono">Verses / Session</div>
        </div>
      </div>
      
      {/* Top Livres & Top Versets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Livres */}
        <div className="glass-copilot p-6">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-5">📖 Most Cited Books</h3>
          
          {statistics.top_books && statistics.top_books.length > 0 ? (
            <div className="space-y-4">
              {statistics.top_books.map((book, index) => (
                <div key={book.book} className="flex items-center">
                  <div className="w-7 h-7 bg-indigo-50 border border-indigo-100 rounded-full flex items-center justify-center font-bold text-indigo-700 mr-3 text-xs">
                    {index + 1}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-slate-700">{book.book}</div>
                    <div className="w-full bg-slate-100 rounded-full h-1 mt-1.5 overflow-hidden">
                      <div
                        className="bg-indigo-500 h-full rounded-full"
                        style={{ width: `${(book.count / statistics.top_books[0].count) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="ml-4 font-bold text-xs text-slate-500">{book.count}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-slate-300 text-center py-6 text-xs">No analytics data available</div>
          )}
        </div>
        
        {/* Top Versets */}
        <div className="glass-copilot p-6">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-5">⭐ Most Cited Verses</h3>
          
          {statistics.top_verses && statistics.top_verses.length > 0 ? (
            <div className="space-y-2.5">
              {statistics.top_verses.map((verse, index) => (
                <div
                  key={verse.reference}
                  className="flex items-center justify-between p-3 bg-slate-50 border border-slate-100 rounded-2xl"
                >
                  <div className="flex items-center space-x-3">
                    <div className="w-6 h-6 bg-purple-50 border border-purple-100 rounded-full flex items-center justify-center text-[10px] font-bold text-purple-700">
                      {index + 1}
                    </div>
                    <span className="font-semibold text-slate-700 text-xs">{verse.reference}</span>
                  </div>
                  <span className="px-2.5 py-1 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-lg text-[10px] font-bold">
                    {verse.count}x
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-slate-300 text-center py-6 text-xs">No analytics data available</div>
          )}
        </div>
      </div>
      
      {/* Versets par jour */}
      <div className="glass-copilot p-6">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-6">📈 Daily Detection Activity</h3>
        
        {statistics.verses_per_day && statistics.verses_per_day.length > 0 ? (
          <div className="h-44 flex items-end space-x-2 pt-6 px-2 border-b border-slate-100">
            {statistics.verses_per_day.map((day) => {
              const maxCount = Math.max(...statistics.verses_per_day.map(d => d.count))
              const height = (day.count / (maxCount || 1)) * 100
              
              return (
                <div
                  key={day.date}
                  className="flex-1 flex flex-col items-center group relative"
                >
                  <div className="absolute bottom-full mb-2 bg-slate-800 text-white text-[9px] font-bold px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap shadow-lg">
                    {day.count} verses
                  </div>
                  
                  <div
                    className="w-full bg-indigo-100 group-hover:bg-indigo-500 rounded-t transition-all duration-200"
                    style={{ height: `${height}%`, minHeight: day.count > 0 ? '5px' : '1px' }}
                  />
                  <div className="text-[8px] text-slate-400 mt-2 font-mono whitespace-nowrap overflow-hidden text-ellipsis max-w-[35px] tracking-tighter">
                    {new Date(day.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-slate-300 text-center py-8 text-xs">No activity data found</div>
        )}
      </div>
    </div>
  )
}
