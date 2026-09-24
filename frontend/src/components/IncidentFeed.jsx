import React, { useState } from 'react'
import { Radio, Send, Loader2 } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const CAT_COLOR = {
  FLOODED_ROAD: 'text-sky-400 bg-sky-500/10',
  TRAPPED_RESIDENTS: 'text-red-400 bg-red-500/10',
  POWER_OUTAGE: 'text-yellow-400 bg-yellow-500/10',
  HOSPITAL_ACCESS_BLOCKED: 'text-rose-400 bg-rose-500/10',
  BRIDGE_COLLAPSE: 'text-red-500 bg-red-500/15',
  LANDSLIDE: 'text-orange-400 bg-orange-500/10',
  EVACUATION_NEEDED: 'text-amber-400 bg-amber-500/10',
  RELIEF_SHELTER_FULL: 'text-purple-400 bg-purple-500/10',
  WATER_CONTAMINATION: 'text-teal-400 bg-teal-500/10',
  COMMUNICATION_DOWN: 'text-slate-400 bg-slate-500/10',
  OTHER: 'text-slate-400 bg-slate-500/10',
}

export default function IncidentFeed() {
  const { incidents, api } = useApp()
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [msg, setMsg] = useState(null)
  const [filter, setFilter] = useState('')
  const [more, setMore] = useState(10)

  const filtered = (incidents || [])
    .filter((i) => (filter ? (i.category || '').includes(filter) || (i.state || '').includes(filter) : true))
    .slice(0, more)

  const submit = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setSubmitting(true)
    setMsg(null)
    try {
      await api.submitIncident(text)
      setMsg({ ok: true, text: 'Incident ingested — NLP parsed and zone score updated.' })
      setText('')
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
        <Radio size={12} /> Live Incident Feed & Citizen Reports
      </h3>

      <form onSubmit={submit} className="mb-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder='e.g. "Heavy flooding in Guwahati near Fancy Bazaar, 4 people stranded on rooftop"'
          className="w-full bg-slate-800 border border-eoc-border rounded-md px-2 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-sky-500 resize-none"
        />
        <div className="flex items-center gap-2 mt-1.5">
          <button
            type="submit"
            disabled={submitting || !text.trim()}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-[10px] font-semibold"
          >
            {submitting ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
            Submit Report
          </button>
          <div className="flex gap-1 ml-auto">
            {['', 'Assam', 'Bihar'].map((f) => (
              <button
                key={f || 'all'}
                onClick={() => setFilter(f)}
                className={`text-[9px] px-2 py-0.5 rounded ${filter === f ? 'bg-sky-500/20 text-sky-300' : 'bg-slate-800 text-slate-500'}`}
              >
                {f || 'All'}
              </button>
            ))}
          </div>
        </div>
        {msg && (
          <p className={`mt-1.5 text-[10px] ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
        )}
      </form>

      <div className="space-y-1.5">
        {filtered.map((inc) => (
          <div key={inc.id} className="rounded-lg bg-slate-800/50 border border-eoc-border p-2">
            <div className="flex items-center gap-1.5 mb-1 flex-wrap">
              <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold ${CAT_COLOR[inc.category] || CAT_COLOR.OTHER}`}>
                {inc.category}
              </span>
              <span className="text-[9px] text-slate-500">{inc.state || '—'} · {inc.location_name}</span>
              <span className="ml-auto text-[9px] font-mono text-slate-500">
                {((inc.severity || 0) * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-[10px] text-slate-300 leading-snug line-clamp-2">{inc.description}</p>
            <div className="flex justify-between mt-1 text-[8px] text-slate-600">
              <span>{new Date(inc.timestamp).toLocaleTimeString('en-IN', { hour12: false })}</span>
              <span>conf {(inc.confidence || 0).toFixed(2)} · {inc.source}</span>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-[10px] text-slate-500 text-center py-2">No incidents yet.</p>
        )}
        {(incidents?.length || 0) > more && (
          <button
            onClick={() => setMore((m) => m + 10)}
            className="w-full text-[10px] text-sky-400 py-1 hover:bg-slate-800/50 rounded transition-colors"
          >
            Load more ({incidents.length - filtered.length} remaining)
          </button>
        )}
      </div>
    </div>
  )
}