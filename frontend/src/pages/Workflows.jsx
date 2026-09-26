import { useCallback, useEffect, useState } from 'react'
import WorkflowDetailsModal from '../components/workflows/WorkflowDetailsModal'
import WorkflowExecutionModal from '../components/workflows/WorkflowExecutionModal'
import {
  getWorkflowExecution,
  listWorkflowExecutions,
  listWorkflows,
  triggerWorkflow,
} from '../services/workflowsApi'
import './Workflows.css'

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function Workflows() {
  const [workflows, setWorkflows] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [executions, setExecutions] = useState([])
  const [loading, setLoading] = useState(true)
  const [execLoading, setExecLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [detailsWorkflow, setDetailsWorkflow] = useState(null)
  const [confirmWorkflow, setConfirmWorkflow] = useState(null)
  const [entityType, setEntityType] = useState('document')
  const [entityId, setEntityId] = useState('')
  const [triggering, setTriggering] = useState(false)
  const [executionDetail, setExecutionDetail] = useState(null)

  const selected = workflows.find((item) => item.id === selectedId) || null

  const loadWorkflows = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const payload = await listWorkflows()
      const items = payload.items || []
      setWorkflows(items)
      setSelectedId((current) => current || items[0]?.id || null)
    } catch (err) {
      setError(err.message || 'Failed to load workflows.')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadExecutions = useCallback(async (workflowId) => {
    if (!workflowId) {
      setExecutions([])
      return
    }
    setExecLoading(true)
    try {
      const payload = await listWorkflowExecutions(workflowId, { page: 1, pageSize: 20 })
      setExecutions(payload.items || [])
    } catch (err) {
      setError(err.message || 'Failed to load executions.')
    } finally {
      setExecLoading(false)
    }
  }, [])

  useEffect(() => {
    loadWorkflows()
  }, [loadWorkflows])

  useEffect(() => {
    if (selectedId) {
      loadExecutions(selectedId)
    }
  }, [selectedId, loadExecutions])

  const openRun = (workflow) => {
    setConfirmWorkflow(workflow)
    setEntityType(
      workflow.trigger_type === 'invoice_extracted'
        ? 'invoice'
        : workflow.trigger_type === 'purchase_order_extracted'
          ? 'purchase_order'
          : workflow.trigger_type === 'review_completed'
            ? 'review'
            : workflow.trigger_type === 'validation_completed'
              ? 'validation'
              : 'document',
    )
    setEntityId('')
    setSuccess('')
  }

  const onConfirmRun = async () => {
    if (!confirmWorkflow || !entityId.trim() || triggering) return
    setTriggering(true)
    setError('')
    setSuccess('')
    try {
      const result = await triggerWorkflow(confirmWorkflow.id, {
        entity_type: entityType,
        entity_id: entityId.trim(),
        force: true,
      })
      setSuccess(`Workflow finished with status: ${result.status}`)
      setConfirmWorkflow(null)
      setSelectedId(confirmWorkflow.id)
      await loadExecutions(confirmWorkflow.id)
      setExecutionDetail(result)
    } catch (err) {
      setError(err.message || 'Failed to trigger workflow.')
    } finally {
      setTriggering(false)
    }
  }

  const openExecution = async (execution) => {
    try {
      const detail = await getWorkflowExecution(execution.id)
      setExecutionDetail(detail)
    } catch (err) {
      setError(err.message || 'Failed to load execution.')
    }
  }

  return (
    <div className="workflows-page">
      <section className="workflows-page__intro">
        <p className="workflows-page__kicker">Automation</p>
        <h2>Workflows</h2>
        <p>
          Controlled predefined workflows only. Actions are allowlisted internal services —
          no shell commands, emails, or arbitrary code.
        </p>
      </section>

      {error && <div className="workflows-page__alert workflows-page__alert--error">{error}</div>}
      {success && <div className="workflows-page__alert workflows-page__alert--success">{success}</div>}

      {loading ? (
        <div className="workflows-page__state">Loading workflows…</div>
      ) : (
        <div className="workflows-page__layout">
          <section className="workflows-page__list">
            <h3>Predefined workflows</h3>
            <ul>
              {workflows.map((workflow) => (
                <li key={workflow.id} className={workflow.id === selectedId ? 'is-active' : ''}>
                  <button type="button" onClick={() => setSelectedId(workflow.id)}>
                    <strong>{workflow.name}</strong>
                    <span>{workflow.trigger_type}</span>
                    <span className="workflows-page__status">{workflow.status}</span>
                  </button>
                  <div className="workflows-page__row-actions">
                    <button type="button" onClick={() => setDetailsWorkflow(workflow)}>
                      Details
                    </button>
                    <button type="button" onClick={() => openRun(workflow)}>
                      Run
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="workflows-page__detail">
            {selected ? (
              <>
                <div className="workflows-page__detail-head">
                  <div>
                    <h3>{selected.name}</h3>
                    <p>{selected.description}</p>
                  </div>
                  <button type="button" className="workflows-page__run" onClick={() => openRun(selected)}>
                    Run Workflow
                  </button>
                </div>
                <dl>
                  <div>
                    <dt>Trigger</dt>
                    <dd>{selected.trigger_type}</dd>
                  </div>
                  <div>
                    <dt>Allowed actions</dt>
                    <dd>{(selected.allowed_actions || []).join(', ') || '—'}</dd>
                  </div>
                </dl>

                <div className="workflows-page__executions">
                  <h4>Recent executions</h4>
                  {execLoading && <p>Loading executions…</p>}
                  {!execLoading && executions.length === 0 && <p>No executions yet.</p>}
                  {!execLoading && executions.length > 0 && (
                    <div className="workflows-page__table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Status</th>
                            <th>Entity</th>
                            <th>Started</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {executions.map((execution) => (
                            <tr key={execution.id}>
                              <td>{execution.status}</td>
                              <td>
                                {execution.entity_type}
                                <br />
                                <span className="workflows-page__muted">{execution.entity_id}</span>
                              </td>
                              <td>{formatDate(execution.started_at)}</td>
                              <td>
                                <button type="button" onClick={() => openExecution(execution)}>
                                  View
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="workflows-page__state">Select a workflow to inspect executions.</div>
            )}
          </section>
        </div>
      )}

      {detailsWorkflow && (
        <WorkflowDetailsModal
          workflow={detailsWorkflow}
          onClose={() => setDetailsWorkflow(null)}
          onRun={(workflow) => {
            setDetailsWorkflow(null)
            openRun(workflow)
          }}
        />
      )}

      {confirmWorkflow && (
        <div className="wf-modal-backdrop" role="presentation">
          <div className="wf-modal" role="dialog" aria-modal="true">
            <div className="wf-modal__header">
              <h3>Confirm workflow run</h3>
              <button type="button" onClick={() => setConfirmWorkflow(null)} aria-label="Close">
                ×
              </button>
            </div>
            <p className="wf-modal__desc">
              Run <strong>{confirmWorkflow.name}</strong>? This executes only predefined internal
              actions ({(confirmWorkflow.allowed_actions || []).join(', ') || 'none'}). No emails,
              shell commands, or external APIs will be called.
            </p>
            <label className="workflows-page__field">
              Entity type
              <select value={entityType} onChange={(event) => setEntityType(event.target.value)}>
                <option value="document">document</option>
                <option value="invoice">invoice</option>
                <option value="purchase_order">purchase_order</option>
                <option value="validation">validation</option>
                <option value="review">review</option>
              </select>
            </label>
            <label className="workflows-page__field">
              Entity ID
              <input
                value={entityId}
                onChange={(event) => setEntityId(event.target.value)}
                placeholder="UUID of the document/invoice/review"
              />
            </label>
            <div className="wf-modal__footer">
              <button type="button" className="wf-modal__secondary" onClick={() => setConfirmWorkflow(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="wf-modal__primary"
                disabled={triggering || !entityId.trim()}
                onClick={onConfirmRun}
              >
                {triggering ? 'Running…' : 'Confirm Run'}
              </button>
            </div>
          </div>
        </div>
      )}

      {executionDetail && (
        <WorkflowExecutionModal
          execution={executionDetail}
          onClose={() => setExecutionDetail(null)}
        />
      )}
    </div>
  )
}

export default Workflows
