import './ProcessingStatus.css'

const STAGES = [
  { key: 'text_extraction', label: 'Text Extraction' },
  { key: 'classification', label: 'Classification' },
  { key: 'structured_extraction', label: 'Structured Extraction' },
  { key: 'line_items', label: 'Line Items' },
]

const STAGE_ORDER = [
  'queued',
  'text_extraction',
  'classification',
  'structured_extraction',
  'line_items',
  'completed',
]

function stageIndex(stage) {
  const index = STAGE_ORDER.indexOf(stage)
  return index === -1 ? 0 : index
}

function markerFor(stageKey, currentStage, status) {
  if (status === 'failed' && stageKey === currentStage) return '✗'
  if (status === 'completed') return '✓'
  const current = stageIndex(currentStage)
  const target = stageIndex(stageKey)
  if (status === 'cancelled') return current >= target ? '○' : '○'
  if (current > target) return '✓'
  if (current === target && (status === 'running' || status === 'queued')) return '●'
  return '○'
}

export default function ProcessingStatus({ job, onRetry, retrying }) {
  if (!job) return null

  const progress = Number.isFinite(job.progress) ? job.progress : 0

  return (
    <div className={`processing-status processing-status--${job.status}`}>
      {job.status === 'completed' && (
        <p className="processing-status__headline">Processing complete ✓</p>
      )}
      {job.status === 'failed' && (
        <div className="processing-status__failed">
          <p className="processing-status__headline">Processing failed</p>
          {job.error_message && (
            <p className="processing-status__reason">Reason: {job.error_message}</p>
          )}
          {onRetry && (
            <button
              type="button"
              className="processing-status__retry"
              onClick={onRetry}
              disabled={retrying}
            >
              {retrying ? 'Retrying…' : 'Retry'}
            </button>
          )}
        </div>
      )}
      {job.status === 'cancelled' && (
        <p className="processing-status__headline">Processing cancelled</p>
      )}
      {(job.status === 'queued' || job.status === 'running') && (
        <p className="processing-status__headline">
          Processing… {progress}%
          {job.current_stage ? ` · ${String(job.current_stage).replaceAll('_', ' ')}` : ''}
        </p>
      )}

      <ul className="processing-status__stages">
        {STAGES.map((stage) => (
          <li key={stage.key}>
            <span className="processing-status__marker" aria-hidden="true">
              {markerFor(stage.key, job.current_stage, job.status)}
            </span>
            {stage.label}
          </li>
        ))}
      </ul>

      {(job.status === 'queued' || job.status === 'running') && (
        <div className="processing-status__bar" aria-hidden="true">
          <div className="processing-status__bar-fill" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  )
}
