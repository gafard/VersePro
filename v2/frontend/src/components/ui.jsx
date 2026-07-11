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
  return <div className={`vp-skeleton ${className}`} style={{ width, height, ...style }} aria-hidden="true" />
}

export function SkeletonRows({ rows = 4, height = 56, gap = 10 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }} role="status" aria-label="Chargement…">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={height} />)}
    </div>
  )
}

/* ── État vide ── */
export function EmptyState({ icon = 'inbox', title, children, action }) {
  return (
    <div className="live-empty" role="status">
      <span style={{ color: 'var(--vp-text-faint)', marginBottom: 4 }}><Icon name={icon} size={22} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

/* ── Toasts : hôte global, alimenté par le store ── */
export function ToastHost() {
  const { toasts, dismissToast } = useStore()
  if (!toasts.length) return null
  return (
    <div className="vp-toast-host" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`vp-toast is-${toast.kind}`}>
          <span className="vp-toast-icon">
            <Icon name={toast.kind === 'error' ? 'alert' : 'check'} size={15} />
          </span>
          <span>{toast.message}</span>
          {toast.action && (
            <button onClick={() => { toast.action.onClick(); dismissToast(toast.id) }}>
              {toast.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
