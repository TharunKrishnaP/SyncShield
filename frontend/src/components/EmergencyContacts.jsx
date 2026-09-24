import React, { useState } from 'react'
import { Phone, Building2, Mail, Globe, Siren } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const CAT_STYLE = {
  emergency: 'border-red-500/40 bg-red-500/10 hover:bg-red-500/20',
  disaster: 'border-orange-500/40 bg-orange-500/10 hover:bg-orange-500/20',
  medical: 'border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20',
  travel: 'border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20',
  welfare: 'border-purple-500/40 bg-purple-500/10 hover:bg-purple-500/20',
}

export default function EmergencyContacts() {
  const { contacts } = useApp()
  const [tab, setTab] = useState('helplines')
  if (!contacts) return null

  const helplines = contacts.helplines || []
  const agencies = contacts.agencies || []

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-eoc-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Siren size={12} className="text-red-400" /> Emergency Contacts
        </h3>
        <div className="flex gap-1">
          <button
            onClick={() => setTab('helplines')}
            className={`text-[9px] px-1.5 py-0.5 rounded ${tab === 'helplines' ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'}`}
          >
            Helplines
          </button>
          <button
            onClick={() => setTab('agencies')}
            className={`text-[9px] px-1.5 py-0.5 rounded ${tab === 'agencies' ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'}`}
          >
            Agencies
          </button>
        </div>
      </div>

      {tab === 'helplines' && (
        <div className="p-2 grid grid-cols-2 gap-1.5">
          {helplines.map((h) => (
            <a
              key={h.number}
              href={`tel:${h.number}`}
              className={`rounded-lg border px-2 py-1.5 transition-colors ${CAT_STYLE[h.category] || CAT_STYLE.travel}`}
            >
              <div className="flex items-center gap-1 text-slate-100 font-extrabold text-[15px] leading-none">
                <Phone size={11} /> {h.number}
              </div>
              <div className="text-[9px] font-semibold text-slate-300 mt-1 leading-tight">{h.label}</div>
              <div className="text-[8px] text-slate-400 leading-tight mt-0.5">{h.plain}</div>
            </a>
          ))}
        </div>
      )}

      {tab === 'agencies' && (
        <div className="p-2 space-y-1.5">
          {agencies.map((a) => (
            <div key={a.name} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="flex items-start gap-1.5">
                <Building2 size={11} className="mt-0.5 text-slate-500 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-[10px] font-bold text-slate-100 leading-snug">{a.name}</div>
                  <div className="text-[9px] text-slate-500">{a.role}</div>
                  {a.plain && <div className="text-[9px] text-slate-400 leading-snug mt-0.5">{a.plain}</div>}
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    {(a.phone || []).map((p) => (
                      <a key={p} href={`tel:${p.replace(/[^0-9+]/g, '')}`} className="text-[9px] text-sky-400 hover:text-sky-300 flex items-center gap-0.5">
                        <Phone size={8} /> {p}
                      </a>
                    ))}
                    {a.email && (
                      <a href={`mailto:${a.email}`} className="text-[9px] text-slate-400 hover:text-slate-200 flex items-center gap-0.5">
                        <Mail size={8} /> {a.email}
                      </a>
                    )}
                    {a.website && (
                      <a href={a.website} target="_blank" rel="noreferrer" className="text-[9px] text-slate-400 hover:text-slate-200 flex items-center gap-0.5">
                        <Globe size={8} /> Website
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
          <p className="text-[8px] text-slate-600 px-1">
            All numbers are published Government of India helplines. State Emergency Operations Centres are reached on 1070.
          </p>
        </div>
      )}
    </div>
  )
}
