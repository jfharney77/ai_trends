function fmt(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export default function RunHistory({ runs, currentId, onOpen }) {
  return (
    <div className="card">
      <h2>History</h2>
      {runs.length === 0 && <p className="hint">No runs yet.</p>}
      <ul className="history">
        {runs.map((r) => (
          <li key={r.id}>
            <button className={`history-item ${r.id === currentId ? 'active' : ''}`} onClick={() => onOpen(r.id)}>
              <span className="history-when">{fmt(r.created_at)}</span>
              <span className={`status status-${r.status}`}>{r.status}</span>
              <span className="history-detail">
                {r.trend_count} trends · {r.provider}/{r.model}
                {r.source === 'cron' ? ' · scheduled' : r.source === 'digest' ? ' · briefing' : ''}
                {r.emailed_to ? ' · emailed' : ''}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
