const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  config: () => request('/api/config'),
  models: (provider) => request(`/api/models?provider=${encodeURIComponent(provider)}`),
  runs: () => request('/api/runs'),
  run: (id) => request(`/api/runs/${id}`),
  createRun: (body) => request('/api/runs', { method: 'POST', body: JSON.stringify(body) }),
  runDigest: () => request('/api/digest', { method: 'POST' }),
  emailRun: (id, to) => request(`/api/runs/${id}/email`, { method: 'POST', body: JSON.stringify({ to }) }),
  digestUrl: (id) => `${BASE}/api/runs/${id}/digest.html`,
}
