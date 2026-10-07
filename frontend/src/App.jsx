import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import RunForm from './components/RunForm.jsx'
import RunResults from './components/RunResults.jsx'
import RunHistory from './components/RunHistory.jsx'

const POLL_MS = 2000

export default function App() {
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState(null)
  const [run, setRun] = useState(null)
  const [runs, setRuns] = useState([])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.runs()
      setRuns(data.runs)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setConfigError(e.message))
    refreshRuns()
  }, [refreshRuns])

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const watchRun = useCallback(
    (id) => {
      stopPolling()
      const tick = async () => {
        try {
          const data = await api.run(id)
          setRun(data)
          if (data.status === 'done' || data.status === 'failed') {
            stopPolling()
            refreshRuns()
          }
        } catch (e) {
          setError(e.message)
          stopPolling()
        }
      }
      tick()
      pollRef.current = setInterval(tick, POLL_MS)
    },
    [refreshRuns],
  )

  useEffect(() => stopPolling, [])

  const startRun = async (body) => {
    setError(null)
    setStarting(true)
    try {
      const { id } = await api.createRun(body)
      watchRun(id)
    } catch (e) {
      setError(e.message)
    } finally {
      setStarting(false)
    }
  }

  const startDigest = async () => {
    setError(null)
    setStarting(true)
    try {
      const { id } = await api.runDigest()
      watchRun(id)
    } catch (e) {
      setError(e.message)
    } finally {
      setStarting(false)
    }
  }

  const openRun = async (id) => {
    setError(null)
    try {
      const data = await api.run(id)
      setRun(data)
      if (data.status === 'queued' || data.status === 'running') watchRun(id)
    } catch (e) {
      setError(e.message)
    }
  }

  const emailRun = async (id, to) => {
    setError(null)
    const result = await api.emailRun(id, to)
    setRun((r) => (r && r.id === id ? { ...r, emailed_to: result.sent_to, email_error: null } : r))
    refreshRuns()
    return result
  }

  const busy = run && (run.status === 'queued' || run.status === 'running')

  return (
    <div className="page">
      <header className="masthead">
        <div>
          <h1>AI Trends</h1>
          <p className="subtitle">
            A LangGraph agent searches the web for what changed in five areas of AI and summarizes it with the model you choose.
          </p>
        </div>
        {config && (
          <div className="meta">
            <span>Search: {config.search_backend}</span>
            <span>
              Daily email: {config.email.configured ? `on, ${config.email.digest_hour}:00 ${config.email.digest_tz}` : 'not configured'}
            </span>
            <button
              className="primary digest-button"
              onClick={startDigest}
              disabled={starting || !!busy || !config.email.configured}
              title={config.email.configured ? `Run all five categories and email ${config.email.to.join(', ')}` : 'Set SMTP_USER and SMTP_PASSWORD in backend/.env'}
            >
              {busy && run?.source === 'digest' ? 'Sending briefing' : 'Send daily briefing now'}
            </button>
          </div>
        )}
      </header>

      {configError && <div className="alert">Backend unreachable: {configError}. Start it with scripts/start_backend.sh.</div>}
      {error && (
        <div className="alert">
          {error} <button className="link" onClick={() => setError(null)}>dismiss</button>
        </div>
      )}

      <main className="layout">
        <aside className="sidebar">
          {config && <RunForm config={config} onStart={startRun} disabled={starting || !!busy} />}
          <RunHistory runs={runs} currentId={run?.id} onOpen={openRun} />
        </aside>
        <section className="content">
          {run ? (
            <RunResults run={run} config={config} onEmail={emailRun} digestUrl={api.digestUrl(run.id)} />
          ) : (
            <div className="empty">
              <h2>No run selected</h2>
              <p>Pick the categories and model on the left and start a run, or open a past run from the history list.</p>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
