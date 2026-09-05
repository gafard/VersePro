import React from 'react'
import { useStore } from '../store.js'

/* ════════════════════════════════════════════════════════════════
   Primitifs UI réutilisables — accessibles, sobres, sans dépendance
   ════════════════════════════════════════════════════════════════ */

/* ── Icônes SVG (trait 1.8, 24×24, currentColor) ── */
const paths = {
  check: <path d="M20 6 9 17l-5-5" />,
  x: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
  alert: <><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></>,
  book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></>,
  folder: <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />,
  refresh: <><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></>,
  screen: <><rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" /></>,
  sparkle: <path d="M12 3l1.9 5.7a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3z" />,
  clock: <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>,
  help: <><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
  inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></>,
  mic: <><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" /><path d="M19 10v1a7 7 0 0 1-14 0v-1" /><line x1="12" y1="19" x2="12" y2="22" /></>,
}

export function Icon({ name, size = 15, className, style }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style} aria-hidden="true"
    >
      {paths[name] || null}
    </svg>
  )
}

/* ── Squelette de chargement ── */
export function Skeleton({ width = '100%', height = 14, style, className = '' }) {
  return (
    <div
      className={`bg-surface-elevated border border-border/30 rounded animate-pulse ${className}`}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  )
}

export function SkeletonRows({ rows = 4, height = 56, gap = 10 }) {
  return (
    <div className="flex flex-col" style={{ gap }} role="status" aria-label="Chargement…">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={height} />)}
    </div>
  )
}

/* ── État vide ── */
export function EmptyState({ icon = 'inbox', title, children, action }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center rounded-card border border-dashed border-border-strong bg-surface-base/40 my-3" role="status">
      <span className="text-text-faint mb-1.5"><Icon name={icon} size={22} /></span>
      <strong className="text-sm font-semibold text-text-primary">{title}</strong>
      {children && <p className="text-xs text-text-muted mt-1 max-w-md leading-relaxed">{children}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

/* ── Toasts : hôte global, alimenté par le store ── */
export function ToastHost() {
  const toasts = useStore(s => s.toasts)
  const dismissToast = useStore(s => s.dismissToast)
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-6 right-6 z-toast flex flex-col gap-2.5 max-w-sm pointer-events-none" role="status" aria-live="polite">
      {toasts.map((toast) => {
        const isError = toast.kind === 'error'
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-card bg-surface-raised border shadow-elev-3 text-sm animate-slide-in ${
              isError
                ? 'border-status-danger/40 text-status-danger bg-status-danger/10'
                : 'border-border-strong text-text-primary'
            }`}
          >
            <span className={`shrink-0 flex items-center justify-center w-6 h-6 rounded-full ${
              isError ? 'bg-status-danger/20 text-status-danger' : 'bg-status-ok/20 text-status-ok'
            }`}>
              <Icon name={isError ? 'alert' : 'check'} size={14} />
            </span>
            <span className="flex-1 font-medium">{toast.message}</span>
            {toast.action && (
              <button
                className="px-2.5 py-1 text-xs font-semibold rounded bg-accent text-accent-ink hover:bg-accent-hover transition-colors ml-2"
                onClick={() => { toast.action.onClick(); dismissToast(toast.id) }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
