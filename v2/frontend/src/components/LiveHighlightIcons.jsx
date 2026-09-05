/* Hallmark · pre-emit critique: P5 H5 E5 S5 R5 V4 */
import React from 'react'

function IconFrame({ size, children }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  )
}

export default function LiveHighlightIcon({ type, size = 15 }) {
  if (type === 'highlight') {
    return (
      <IconFrame size={size}>
        <path d="m15.4 4.6 4 4-8.8 8.8-4.7.7.7-4.7 8.8-8.8Z" />
        <path d="m13.8 6.2 4 4" />
        <path d="M3 21h12" />
      </IconFrame>
    )
  }

  if (type === 'underline') {
    return (
      <IconFrame size={size}>
        <path d="M7 4v6a5 5 0 0 0 10 0V4" />
        <path d="M5 21h14" />
      </IconFrame>
    )
  }

  if (type === 'circle') {
    return (
      <IconFrame size={size}>
        <ellipse cx="12" cy="12" rx="9" ry="7" />
        <path d="M8 10h8M9.5 14h5" />
      </IconFrame>
    )
  }

  return (
    <IconFrame size={size}>
      <path d="m7.2 16.8-2.6-2.6a2 2 0 0 1 0-2.8l7.8-7.8a2 2 0 0 1 2.8 0l5.2 5.2a2 2 0 0 1 0 2.8l-5.2 5.2a2 2 0 0 1-2.8 0L7.2 11.6" />
      <path d="M9.8 19H21" />
    </IconFrame>
  )
}
