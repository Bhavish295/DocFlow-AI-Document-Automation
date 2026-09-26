import './WorkflowDetailsModal.css'

function WorkflowDetailsModal({ workflow, onClose, onRun }) {
  if (!workflow) return null

  return (
    <div className="wf-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="wf-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wf-details-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="wf-modal__header">
          <h3 id="wf-details-title">{workflow.name}</h3>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <p className="wf-modal__desc">{workflow.description}</p>
        <dl className="wf-modal__meta">
          <div>
            <dt>Code</dt>
            <dd>{workflow.code}</dd>
          </div>
          <div>
            <dt>Trigger</dt>
            <dd>{workflow.trigger_type}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{workflow.status}</dd>
          </div>
        </dl>
        <div className="wf-modal__actions-list">
          <h4>Allowed actions</h4>
          <ul>
            {(workflow.allowed_actions || []).map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
        <div className="wf-modal__footer">
          <button type="button" className="wf-modal__secondary" onClick={onClose}>
            Close
          </button>
          <button type="button" className="wf-modal__primary" onClick={() => onRun(workflow)}>
            Run Workflow
          </button>
        </div>
      </div>
    </div>
  )
}

export default WorkflowDetailsModal
