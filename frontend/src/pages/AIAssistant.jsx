import { useState } from 'react'
import { Link } from 'react-router-dom'
import SQLResultTable from '../components/ai/SQLResultTable'
import InvestigationResults from '../components/investigation/InvestigationResults'
import { askAgent } from '../services/agentApi'
import { askInvestigation } from '../services/investigationApi'
import { askQuestion } from '../services/ragApi'
import { askBusinessDataQuestion } from '../services/sqlApi'
import './AIAssistant.css'

const INVESTIGATION_EXAMPLES = [
  'Why are invoices being sent to review?',
  'Which vendors have the most invoice validation mismatches?',
  'Which documents require attention?',
  'Show repeated issues with vendors',
]

const AGENT_EXAMPLES = [
  'Why is invoice INV-1827 in review?',
  'Investigate invoice INV-1827.',
  'Find unusual invoices.',
  'Find invoices over 500000 and explain suspicious ones.',
  'How many invoices do we have?',
]

function formatPercent(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(Number(value) * 100)}%`
}

function AIAssistant() {
  const [mode, setMode] = useState('documents')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [ragResult, setRagResult] = useState(null)
  const [sqlResult, setSqlResult] = useState(null)
  const [investigationResult, setInvestigationResult] = useState(null)
  const [agentResult, setAgentResult] = useState(null)
  const [agentConversationId, setAgentConversationId] = useState(null)

  const isDocuments = mode === 'documents'
  const isBusiness = mode === 'business'
  const isInvestigation = mode === 'investigation'
  const isAgent = mode === 'agent'

  const placeholder = isDocuments
    ? 'What are the payment terms mentioned in our documents?'
    : isBusiness
      ? 'How many invoices do we have?'
      : isInvestigation
        ? 'Why are invoices being sent to review?'
        : 'Why is invoice INV-1827 in review?'

  const description = isDocuments
    ? 'Ask questions about processed company documents. Answers are grounded in retrieved document excerpts and include source citations.'
    : isBusiness
      ? 'Ask questions about structured business data such as invoices, purchase orders, vendors, and validations. Queries are read-only and validated before execution.'
      : isInvestigation
        ? 'Run a read-only investigation across review, validation, vendor, and document data. Findings are based only on returned query evidence.'
        : 'Controlled multi-step agent that plans and calls registered read-only tools only. No destructive actions, arbitrary code, or external paid AI.'

  const onModeChange = (nextMode) => {
    setMode(nextMode)
    setError('')
    setRagResult(null)
    setSqlResult(null)
    setInvestigationResult(null)
    setAgentResult(null)
  }

  const onAsk = async (event) => {
    event.preventDefault()
    const cleaned = question.trim()
    if (!cleaned || loading) return

    setLoading(true)
    setError('')
    setRagResult(null)
    setSqlResult(null)
    setInvestigationResult(null)
    setAgentResult(null)
    try {
      if (isDocuments) {
        const payload = await askQuestion({ question: cleaned })
        setRagResult(payload)
      } else if (isBusiness) {
        const payload = await askBusinessDataQuestion({ question: cleaned })
        setSqlResult(payload)
        if (payload.status && payload.status !== 'success' && payload.status !== 'unsupported') {
          setError(payload.answer || 'Unable to answer that business data question.')
        }
      } else if (isInvestigation) {
        const payload = await askInvestigation({ question: cleaned })
        setInvestigationResult(payload)
        if (payload.status === 'failed') {
          setError(payload.summary || 'Investigation failed.')
        }
      } else {
        const payload = await askAgent({
          question: cleaned,
          conversationId: agentConversationId || undefined,
        })
        setAgentResult(payload)
        if (payload.conversation_id) {
          setAgentConversationId(payload.conversation_id)
        }
        if (payload.status === 'failed' || payload.status === 'permission_denied') {
          setError(payload.answer || 'Agent request failed.')
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to get an answer.')
    } finally {
      setLoading(false)
    }
  }

  const hasResult = ragResult || sqlResult || investigationResult || agentResult

  return (
    <div className="ai-assistant">
      <section className="ai-assistant__intro">
        <p className="ai-assistant__kicker">Knowledge</p>
        <h2 className="ai-assistant__title">AI Assistant</h2>
        <p className="ai-assistant__desc">{description}</p>
      </section>

      <div className="ai-assistant__modes" role="tablist" aria-label="Assistant mode">
        <button
          type="button"
          role="tab"
          aria-selected={isDocuments}
          className={isDocuments ? 'is-active' : ''}
          onClick={() => onModeChange('documents')}
        >
          Document Knowledge
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isBusiness}
          className={isBusiness ? 'is-active' : ''}
          onClick={() => onModeChange('business')}
        >
          Business Data
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isInvestigation}
          className={isInvestigation ? 'is-active' : ''}
          onClick={() => onModeChange('investigation')}
        >
          Investigation
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isAgent}
          className={isAgent ? 'is-active' : ''}
          onClick={() => onModeChange('agent')}
        >
          Controlled Agent
        </button>
      </div>

      <section className="ai-assistant__ask">
        <form onSubmit={onAsk}>
          <label htmlFor="ai-question">Your question</label>
          <textarea
            id="ai-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={4}
            placeholder={placeholder}
          />
          {isInvestigation && (
            <div className="ai-assistant__examples">
              <p>Example investigations</p>
              <div>
                {INVESTIGATION_EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="ai-assistant__example"
                    onClick={() => setQuestion(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          {isAgent && (
            <div className="ai-assistant__examples">
              <p>Example agent requests</p>
              <div>
                {AGENT_EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="ai-assistant__example"
                    onClick={() => setQuestion(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          <button type="submit" disabled={loading || !question.trim()}>
            {loading
              ? isDocuments
                ? 'Searching documents…'
                : isBusiness
                  ? 'Querying business data…'
                  : isInvestigation
                    ? 'Running investigation…'
                    : 'Running controlled agent…'
              : isInvestigation
                ? 'Investigate'
                : isAgent
                  ? 'Run Agent'
                  : 'Ask'}
          </button>
        </form>
      </section>

      {error && <div className="ai-assistant__alert ai-assistant__alert--error">{error}</div>}

      {!hasResult && !loading && !error && (
        <div className="ai-assistant__state">
          {isDocuments
            ? 'Ask a question to search indexed document knowledge.'
            : isBusiness
              ? 'Ask a question about invoices, vendors, purchase orders, or validations.'
              : isInvestigation
                ? 'Ask an investigation question about reviews, mismatches, vendors, or documents needing attention.'
                : 'Ask the controlled agent to orchestrate registered read-only tools for invoice review, anomalies, SQL, or knowledge questions.'}
        </div>
      )}

      {loading && (
        <div className="ai-assistant__state">
          {isDocuments
            ? 'Retrieving relevant document context…'
            : isBusiness
              ? 'Generating and validating a read-only query…'
              : isInvestigation
                ? 'Planning and running read-only investigation queries…'
                : 'Planning and executing registered tools within the step limit…'}
        </div>
      )}

      {ragResult && isDocuments && (
        <section className="ai-assistant__answer" aria-live="polite">
          <h3>Answer</h3>
          <p className="ai-assistant__answer-text">{ragResult.answer}</p>

          <div className="ai-assistant__sources">
            <h3>Sources</h3>
            {(!ragResult.sources || ragResult.sources.length === 0) && (
              <p className="ai-assistant__empty-sources">No source documents were retrieved.</p>
            )}
            {ragResult.sources?.length > 0 && (
              <ul>
                {ragResult.sources.map((source) => (
                  <li key={`${source.chunk_id}`}>
                    <div className="ai-assistant__source-top">
                      <strong>{source.filename}</strong>
                      <span>{formatPercent(source.similarity)} relevant</span>
                    </div>
                    <p className="ai-assistant__source-meta">
                      {source.document_type || 'unknown type'} · chunk reference{' '}
                      {String(source.chunk_id).slice(0, 8)}
                    </p>
                    <p className="ai-assistant__source-excerpt">{source.content}</p>
                    <Link to="/documents">Open Documents</Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {sqlResult && isBusiness && (
        <section className="ai-assistant__answer" aria-live="polite">
          <h3>Answer</h3>
          <p className="ai-assistant__answer-text">{sqlResult.answer}</p>
          <p className="ai-assistant__source-meta">
            Status: {sqlResult.status}
            {typeof sqlResult.row_count === 'number' ? ` · ${sqlResult.row_count} row(s)` : ''}
          </p>

          <div className="ai-assistant__sql-results">
            <h3>Results</h3>
            <SQLResultTable
              columns={sqlResult.columns}
              rows={sqlResult.rows}
              emptyMessage="No rows returned for this question."
            />
          </div>

          {sqlResult.sql && (
            <details className="ai-assistant__sql-view">
              <summary>View SQL</summary>
              <pre>{sqlResult.sql}</pre>
            </details>
          )}
        </section>
      )}

      {investigationResult && isInvestigation && (
        <InvestigationResults result={investigationResult} />
      )}

      {agentResult && isAgent && (
        <section className="ai-assistant__answer ai-assistant__agent" aria-live="polite">
          <h3>Agent answer</h3>
          <p className="ai-assistant__answer-text" style={{ whiteSpace: 'pre-wrap' }}>
            {agentResult.answer}
          </p>
          <p className="ai-assistant__source-meta">
            Status: {agentResult.status}
            {agentResult.tools_used?.length
              ? ` · tools: ${agentResult.tools_used.join(', ')}`
              : ''}
          </p>

          {agentResult.warnings?.length > 0 && (
            <div className="ai-assistant__agent-warnings">
              <h3>Warnings</h3>
              <ul>
                {agentResult.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="ai-assistant__agent-steps">
            <h3>Steps</h3>
            {(!agentResult.steps || agentResult.steps.length === 0) && (
              <p className="ai-assistant__empty-sources">No tool steps were executed.</p>
            )}
            {agentResult.steps?.length > 0 && (
              <ol>
                {agentResult.steps.map((step) => (
                  <li key={`${step.step_number}-${step.tool_name}`}>
                    <strong>
                      {step.step_number}. {step.tool_name}
                    </strong>{' '}
                    <span className={`ai-assistant__agent-status ai-assistant__agent-status--${step.status}`}>
                      {step.status}
                    </span>
                    <div className="ai-assistant__source-meta">{step.purpose}</div>
                    <div>{step.concise_result_summary}</div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {agentResult.evidence?.length > 0 && (
            <div className="ai-assistant__agent-evidence">
              <h3>Evidence</h3>
              <ul>
                {agentResult.evidence.map((item, index) => (
                  <li key={`${item.source}-${index}`}>
                    <strong>{item.source}</strong>
                    <div>{item.summary}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default AIAssistant
