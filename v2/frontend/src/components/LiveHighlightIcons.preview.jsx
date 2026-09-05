import React from 'react'
import LiveHighlightIcon from './LiveHighlightIcons.jsx'

const states = [
  ['default', null],
  ['hover', 'is-hover'],
  ['focus', 'is-focus'],
  ['active', 'is-active'],
  ['disabled', null],
  ['loading', 'loading'],
  ['error', 'error'],
  ['success', 'success'],
]

/** Aperçu de développement Hallmark : non importé par l'application. */
export default function LiveHighlightIconsPreview() {
  return (
    <section className="live-annotation-preview" aria-label="Surlignage Live — huit états">
      <h1>Surlignage Live — huit états</h1>
      {states.map(([label, state]) => (
        <div className="live-annotation-preview-row" key={label}>
          <code>{label}</code>
          <button
            type="button"
            className={`live-annotation-button is-highlight ${state?.startsWith('is-') ? state : ''}`}
            data-state={state && !state.startsWith('is-') ? state : undefined}
            disabled={label === 'disabled'}
            aria-busy={label === 'loading' || undefined}
          >
            <LiveHighlightIcon type="highlight" />
            <span>{label === 'loading' ? 'Application…' : 'Surligner'}</span>
          </button>
        </div>
      ))}
    </section>
  )
}
