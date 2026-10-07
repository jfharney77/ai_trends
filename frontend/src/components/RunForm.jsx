import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function RunForm({ config, onStart, disabled }) {
  const providers = Object.keys(config.providers)
  const firstUsable = config.providers[config.default_provider]?.configured
    ? config.default_provider
    : providers.find((p) => config.providers[p].configured) || config.default_provider

  const [selected, setSelected] = useState(() => new Set(config.categories.map((c) => c.id)))
  const [provider, setProvider] = useState(firstUsable)
  const [model, setModel] = useState(config.providers[firstUsable]?.default_model || '')
  const [models, setModels] = useState([])
  const [modelsError, setModelsError] = useState(null)
  const [email, setEmail] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .models(provider)
      .then((d) => !cancelled && setModels(d.models))
      .catch((e) => !cancelled && setModelsError(e.message))
    return () => {
      cancelled = true
    }
  }, [provider])

  const changeProvider = (next) => {
    setProvider(next)
    setModel(config.providers[next]?.default_model || '')
    setModels([])
    setModelsError(null)
  }

  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const allSelected = selected.size === config.categories.length
  const providerInfo = config.providers[provider]

  const submit = (e) => {
    e.preventDefault()
    if (selected.size === 0) return
    onStart({
      category_ids: allSelected ? [] : [...selected],
      provider,
      model: model || null,
      email,
    })
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>New run</h2>

      <div className="field">
        <div className="field-head">
          <label>Categories</label>
          <button
            type="button"
            className="link"
            onClick={() => setSelected(allSelected ? new Set() : new Set(config.categories.map((c) => c.id)))}
          >
            {allSelected ? 'Clear' : 'Select all'}
          </button>
        </div>
        {config.categories.map((c) => (
          <label key={c.id} className="check" title={c.description}>
            <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
            <span>{c.label}</span>
          </label>
        ))}
      </div>

      <div className="field">
        <label htmlFor="provider">Provider</label>
        <select id="provider" value={provider} onChange={(e) => changeProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
              {config.providers[p].configured ? '' : ' (not configured)'}
            </option>
          ))}
        </select>
        {!providerInfo?.configured && <p className="hint warn">{providerInfo?.error}</p>}
      </div>

      <div className="field">
        <label htmlFor="model">Model</label>
        <input id="model" list="model-options" value={model} onChange={(e) => setModel(e.target.value)} placeholder={providerInfo?.default_model} />
        <datalist id="model-options">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        {modelsError ? (
          <p className="hint">Could not load model list. Type a model name.</p>
        ) : models.length > 0 ? (
          <p className="hint">{models.length} models available. Start typing to filter.</p>
        ) : null}
      </div>

      <label className="check">
        <input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} disabled={!config.email.configured} />
        <span>
          Email results to {config.email.to.join(', ')}
          {!config.email.configured && ' (set SMTP in .env)'}
        </span>
      </label>

      <button type="submit" className="primary" disabled={disabled || selected.size === 0 || !providerInfo?.configured}>
        {disabled ? 'Running' : 'Run agent'}
      </button>
    </form>
  )
}
