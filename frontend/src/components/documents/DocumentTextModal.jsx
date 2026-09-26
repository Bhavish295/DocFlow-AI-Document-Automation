import { useEffect } from 'react'
import './DocumentTextModal.css'

function DocumentTextModal({ open, title, status, text, error, loading, onClose }) {
  useEffect(() => {
    if (!open) return undefined

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) {
    return null
  }

  return (
    <div className="text-modal" role="presentation" onClick={onClose}>
      <div
        className="text-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-text-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="text-modal__header">
          <div>
            <p className="text-modal__eyebrow">Extracted text</p>
            <h2 id="document-text-title" className="text-modal__title">
              {title}
            </h2>
          </div>
          <button type="button" className="text-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="text-modal__meta">
          <span className={`text-modal__status text-modal__status--${status || 'uploaded'}`}>
            {(status || 'unknown').replaceAll('_', ' ')}
          </span>
        </div>

        <div className="text-modal__body">
          {loading && <p className="text-modal__state">Loading extracted text…</p>}

          {!loading && error && (
            <p className="text-modal__state text-modal__state--error">{error}</p>
          )}

          {!loading && !error && !text && (
            <p className="text-modal__state">
              No extracted text is available for this document yet.
            </p>
          )}

          {!loading && !error && text && (
            <pre className="text-modal__content">{text}</pre>
          )}
        </div>
      </div>
    </div>
  )
}

export default DocumentTextModal
