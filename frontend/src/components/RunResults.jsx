import { useState } from 'react'

function domain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function fmt(iso) {
  return iso ? new Date(iso).toLocaleString() : ''
}

export default function RunResults({ run, config, onEmail, digestUrl }) {
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(null)
  const [sendError, setSendError] = useState(null)
  const [to, setTo] = useState('')

  const labelOf = (id) => config?.categories.find((c) => c.id === id)?.label || id
  const active = run.status === 'queued' || run.status === 'running'
  const resultsById = Object.fromEntries((run.results || []).map((r) => [r.category_id, r]))
  const order = run.category_ids?.length ? run.category_ids : Object.keys(resultsById)

  const send = async () => {
    setSending(true)
    setSendError(null)
    setSent(null)
    try {
      const recipients = to.split(',').map((s) => s.trim()).filter(Boolean)
      const res = await onEmail(run.id, recipients.length ? recipients : null)
      setSent(res.sent_to)
    } catch (e) {
      setSendError(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="results">
      <div className="results-head">
        <div>
          <h2>
            Run {fmt(run.created_at)} <span className={`status status-${run.status}`}>{run.status}</span>
          </h2>
          <p className="hint">
            {run.provider}/{run.model}
            {run.source === 'cron' ? ' · scheduled run' : run.source === 'digest' ? ' · daily briefing, emailing on completion' : ''}
            {run.finished_at ? ` · finished ${fmt(run.finished_at)}` : ''}
          </p>
        </div>
        {run.status === 'done' && (
          <div className="actions">
            <a className="button" href={digestUrl} target="_blank" rel="noreferrer">
              Preview email
            </a>
            <input
              className="to"
              placeholder={config?.email?.to?.join(', ') || 'recipient@example.com'}
              value={to}
              onChange={(e) => setTo(e.target.value)}
              disabled={!config?.email?.configured}
            />
            <button className="primary" onClick={send} disabled={sending || !config?.email?.configured}>
              {sending ? 'Sending' : 'Send email'}
            </button>
          </div>
        )}
      </div>
      {!config?.email?.configured && run.status === 'done' && <p className="hint">Email is off until SMTP settings are added to backend/.env.</p>}
      {sent && <div className="notice">Sent to {sent.join(', ')}.</div>}
      {sendError && <div className="alert">Email failed: {sendError}</div>}
      {run.emailed_to && !sent && <div className="notice">Emailed to {run.emailed_to.join(', ')}.</div>}
      {run.email_error && <div className="alert">Automatic email failed: {run.email_error}</div>}
      {run.error && <div className="alert">Run failed: {run.error}</div>}

      {active && (
        <ul className="progress">
          {order.map((id) => {
            const state = run.progress?.[id] || 'pending'
            return (
              <li key={id} className={`progress-${state}`}>
                <span className="dot" /> {labelOf(id)} <span className="hint">{state === 'pending' ? 'searching and summarizing' : state}</span>
              </li>
            )
          })}
          <li className={run.overview ? 'progress-done' : 'progress-pending'}>
            <span className="dot" /> Overview <span className="hint">{run.overview ? 'done' : 'waiting for categories'}</span>
          </li>
        </ul>
      )}

      {run.overview && (
        <section className="overview">
          <h3>Today at a glance</h3>
          <p>{run.overview}</p>
        </section>
      )}

      {order.map((id) => {
        const r = resultsById[id]
        if (!r) return null
        return (
          <section key={id} className="category">
            <h3>{r.category_label || labelOf(id)}</h3>
            {r.headline && <p className="headline">{r.headline}</p>}
            {r.error && <div className="alert">{r.error}</div>}
            {r.trends?.length === 0 && !r.error && <p className="hint">No trends found. {r.search_result_count} search results were reviewed.</p>}
            <div className="trends">
              {r.trends?.map((t, i) => (
                <article key={i} className="trend">
                  <h4>{t.title}</h4>
                  <p>{t.summary}</p>
                  {t.why_it_matters && (
                    <p className="why">
                      <span>Why it matters</span> {t.why_it_matters}
                    </p>
                  )}
                  <div className="sources">
                    {t.sources?.map((u) => (
                      <a key={u} href={u} target="_blank" rel="noreferrer" title={u}>
                        {domain(u)}
                        {t.verified_sources && !t.verified_sources.includes(u) && <sup title="URL was not in the search results">?</sup>}
                      </a>
                    ))}
                  </div>
                </article>
              ))}
            </div>
            {r.sources?.length > 0 && (
              <details className="raw-sources">
                <summary>{r.search_result_count} search results reviewed</summary>
                <ul>
                  {r.sources.map((s) => (
                    <li key={s.url}>
                      <a href={s.url} target="_blank" rel="noreferrer">
                        {s.title || s.url}
                      </a>
                      {s.published && <span className="hint"> {s.published.slice(0, 10)}</span>}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        )
      })}
    </div>
  )
}
