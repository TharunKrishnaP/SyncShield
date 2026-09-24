import React, { useState } from 'react'
import { LifeBuoy, Users } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import EmergencyContacts from './EmergencyContacts.jsx'
import SafetyRouter from './SafetyRouter.jsx'
import EvacuationPanel from './EvacuationPanel.jsx'
import CitizenServices from './CitizenServices.jsx'

export default function EmergencyPanel() {
  const { contacts } = useApp()
  const rules = contacts?.safety_rules || []
  const [citizenOpen, setCitizenOpen] = useState(false)

  return (
    <div className="flex flex-col min-h-0">
      <div className="px-2 pt-0.5 pb-2 flex items-center justify-between">
        <h2 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <LifeBuoy size={13} className="text-red-400" /> Emergency &amp; Evacuation
        </h2>
        <button
          onClick={() => setCitizenOpen(true)}
          className="flex items-center gap-1.5 text-[9px] font-bold bg-green-600/20 hover:bg-green-600/40 text-green-300 border border-green-500/40 rounded-lg px-2 py-1 transition-colors"
        >
          <Users size={10} /> Citizen Services
        </button>
      </div>
      <div className="flex flex-col gap-3">
        <EmergencyContacts />
        {rules.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-2.5">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5 mb-1.5">
              ⚠ Safety rules
            </h3>
            <ul className="space-y-1">
              {rules.map((r, i) => (
                <li key={i} className="text-[10px] text-slate-300 flex gap-1.5 leading-snug">
                  <span className="mt-1 w-1 h-1 rounded-full bg-amber-400 shrink-0" />
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}
        <SafetyRouter />
        <EvacuationPanel />
      </div>
      {citizenOpen && <CitizenServices onClose={() => setCitizenOpen(false)} />}
    </div>
  )
}