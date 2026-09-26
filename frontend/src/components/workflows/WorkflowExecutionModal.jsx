import './WorkflowExecutionModal.css'

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function WorkflowExecutionModal({ execution, onClose }) {
  if (!execution) return null

  return (
    <div className="wf-exec-backdrop" role="presentation" onClick={onClose}>
      <div
        className="wf-exec-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wf-exec-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="wf-exec-modal__header">
          <h3 id="wf-exec-title">Execution details</h3>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <dl className="wf-exec-modal__meta">
          <div>
            <dt>Workflow</dt>
            <dd>{execution.workflow_name || execution.workflow_code}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{execution.status}</dd>
          </div>
          <div>
            <dt>Trigger</dt>
            <dd>{execution.trigger_event}</dd>
          </div>
          <div>
            <dt>Entity</dt>
            <dd>
              {execution.entity_type} / {execution.entity_id}
            </dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{formatDate(execution.started_at)}</dd>
          </div>
          <div>
            <dt>Completed</dt>
            <dd>{formatDate(execution.completed_at)}</dd>
          </div>
        </dl>

        {execution.error_message && (
          <div className="wf-exec-modal__error">{execution.error_message}</div>
        )}

        <div className="wf-exec-modal__steps">
          <h4>Steps</h4>
          {(!execution.steps || execution.steps.length === 0) && <p>No step records.</p>}
          <ul>
            {execution.steps?.map((step) => (
              <li key={step.id}>
                <div className="wf-exec-modal__step-top">
                  <strong>{step.step_name}</strong>
                  <span>{step.status}</span>
                </div>
                <p>
                  {step.step_type} · {formatDate(step.started_at)}
                </p>
                {step.error_message && <p className="wf-exec-modal__error">{step.error_message}</p>}
                {step.result && (
                  <pre>{JSON.stringify(step.result, null, 2)}</pre>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="wf-exec-modal__footer">
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export default WorkflowExecutionModal
