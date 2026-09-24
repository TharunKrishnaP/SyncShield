import React, { useState } from 'react'
import {
  X,
  MapPin,
  Camera,
  Send,
  Phone,
  ShieldAlert,
  CheckCircle2,
  BedDouble,
  LifeBuoy,
  Siren,
  LocateFixed,
} from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const RISK_CHIP = {
  LOW: 'bg-green-500/15 text-green-300 border-green-500/30',
  MODERATE: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  HIGH: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  VERY_HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
  CRITICAL: 'bg-red-600/20 text-red-200 border-red-500/50',
}

export default function CitizenServices({ onClose }) {
  const { api } = useApp()
  const [tab, setTab] = useState('area')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  // area check
  const [lat, setLat] = useState('25.59')
  const [lon, setLon] = useState('85.14')
  const [area, setArea] = useState(null)

  // report
  const [txt, setTxt] = useState('')
  const [phone, setPhone] = useState('')
  const [photo, setPhoto] = useState(null)
  const [photoUrl, setPhotoUrl] = useState('')
  const [ticket, setTicket] = useState(null)

  const runAreaCheck = async () => {
    const la = parseFloat(lat)
    const lo = parseFloat(lon)
    if (Number.isNaN(la) || Number.isNaN(lo)) {
      setErr('Please enter a valid latitude and longitude.')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const res = await api.areaCheck({ latitude: la, longitude: lo, language: 'en' })
      setArea(res)
    } catch (e) {
      setErr(e.message || 'Area check failed. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setErr('Geolocation is not available in this browser.')
      return
    }
    setBusy(true)
    setErr('')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(4))
        setLon(pos.coords.longitude.toFixed(4))
        setBusy(false)
      },
      (e) => {
        setErr(`Could not get location: ${e.message}. Enter coordinates manually.`)
        setBusy(false)
      },
      { timeout: 8000, maximumAge: 60000 },
    )
  }

  const submitReport = async () => {
    if (!txt.trim()) {
      setErr('Please describe what you are seeing.')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const form = new FormData()
      form.append('text', txt.trim())
      if (phone.trim()) form.append('contact', phone.trim())
      form.append('language', 'en')
      if (photo) form.append('photo', photo)
      const res = await api.citizenReport(form)
      setTicket(res)
      setTxt('')
      setPhone('')
      setPhoto(null)
      setPhotoUrl('')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/70 p-4 isolate">
      <div className="w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-2xl border border-eoc-border bg-eoc-panel shadow-2xl [transform:translateZ(0)] isolate">
        <div className="flex items-center justify-between px-4 py-3 border-b border-eoc-border sticky top-0 bg-eoc-panel">
          <h3 className="text-[12px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <ShieldAlert size={14} className="text-green-400" /> Citizen Services
          </h3>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-slate-700/40">
            <X size={16} />
          </button>
        </div>

        <div className="flex gap-2 px-4 pt-3">
          {[
            { key: 'area', label: 'Check my area', Icon: MapPin },
            { key: 'report', label: 'Report flooding', Icon: Camera },
          ].map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => {
                setTab(key)
                setErr('')
              }}
              className={`flex items-center gap-1.5 text-[11px] font-semibold px-3 py-1.5 rounded-lg border transition-colors ${
                tab === key
                  ? 'bg-green-500/15 text-green-300 border-green-500/40'
                  : 'bg-slate-800/60 text-slate-400 border-eoc-border hover:bg-slate-700/40'
              }`}
            >
              <Icon size={12} /> {label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {tab === 'area' && (
            <div className="space-y-3">
              <p className="text-[11px] text-slate-400 leading-snug">
                Enter where you are. The system checks the nearest monitoring
                station, flood risk, shelters and helplines for that spot.
              </p>
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  placeholder="Latitude"
                  className="bg-slate-900/60 border border-eoc-border rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200"
                />
                <input
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  placeholder="Longitude"
                  className="bg-slate-900/60 border border-eoc-border rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200"
                />
              </div>
              <button
                onClick={useMyLocation}
                disabled={busy}
                className="w-full flex items-center justify-center gap-1.5 text-[11px] font-semibold bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 border border-eoc-border rounded-lg py-1.5"
              >
                <LocateFixed size={13} /> Use my current location
              </button>
              <button
                onClick={runAreaCheck}
                disabled={busy}
                className="w-full flex items-center justify-center gap-1.5 text-[12px] font-bold bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white rounded-lg py-2"
              >
                <MapPin size={13} /> {busy ? 'Checking…' : 'Check risk at this location'}
              </button>

              {area && (
                <div className="space-y-2 rounded-xl border border-eoc-border bg-slate-900/50 p-3">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="text-[12px] font-bold text-slate-100 truncate">{area.zone_name}</div>
                      <div className="text-[10px] text-slate-500 truncate">
                        {area.location?.region_name || area.district}, {area.state} · {area.basin} basin
                      </div>
                      <div className="text-[9px] text-slate-500">
                        ~{area.distance_km_covered} km from zone centre · coverage {area.confidence ?? '—'}%
                        {area.location?.region_type && area.location.region_type !== 'priority_zone'
                          ? ` · nearest ${area.location.region_type.replace('_', ' ')} ${area.location.distance_km} km`
                          : ''}
                      </div>
                    </div>
                    <span className={`text-[10px] px-2 py-1 rounded border font-bold shrink-0 ${RISK_CHIP[area.risk.level] || RISK_CHIP.LOW}`}>
                      {area.risk.level_plain}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-300 bg-slate-800/60 rounded-lg p-2 leading-snug">
                    {area.guidance?.[0] || 'Stay alert and follow NDMA guidance.'}
                  </div>

                  {area.nearby_rivers?.map((r) => (
                    <div key={r.station} className="flex items-center justify-between text-[10px] bg-slate-800/60 rounded-lg px-2 py-1.5">
                      <span className="text-slate-300">
                        {r.river} <span className="text-slate-500">near you ({r.distance_km} km)</span>
                      </span>
                      <span className="text-slate-400">
                        {r.water_level} m · <b className={r.status === 'SEVERE' || r.status === 'EXTREME' ? 'text-orange-400' : 'text-green-400'}>{r.status}</b>
                      </span>
                    </div>
                  ))}

                  <div className="flex items-start gap-1.5 text-[10px] text-sky-300 bg-sky-500/10 rounded-lg p-2">
                    <BedDouble size={11} className="mt-0.5 shrink-0" />
                    <span>
                      {area.shelters?.map((s) => `${s.name} (${s.distance_km} km)`).join(' · ') || 'No shelter close by'}
                    </span>
                  </div>
                  <div className="flex items-start gap-1.5 text-[10px] text-amber-300 bg-amber-500/10 rounded-lg p-2">
                    <Siren size={11} className="mt-0.5 shrink-0" />
                    <span>
                      {area.rescue_bases?.map((b) => `${b.name} (${b.distance_km} km)`).join(' · ') || 'No rescue base close by'}
                    </span>
                  </div>
                  <div className="flex items-start gap-1.5 text-[10px] text-red-300 bg-red-500/10 rounded-lg p-2">
                    <Phone size={11} className="mt-0.5 shrink-0" />
                    <span>{area.helplines?.map((h) => `${h.label} ${h.number}`).slice(0, 3).join(' · ')}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === 'report' && (
            <div className="space-y-3">
              <p className="text-[11px] text-slate-400 leading-snug">
                Tell us what is happening near you. A photo helps officials
                verify quickly. You get a ticket number to track your report.
              </p>
              <textarea
                value={txt}
                onChange={(e) => setTxt(e.target.value)}
                rows={3}
                placeholder={'e.g. Water entering houses near Gandhi Maidan, Patna, 5 families stuck on first floor'}
                className="w-full bg-slate-900/60 border border-eoc-border rounded-lg px-2.5 py-2 text-[12px] text-slate-200 resize-none"
              />
              <div className="flex items-center gap-2">
                <Phone size={13} className="text-slate-500" />
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="Phone (optional)"
                  className="flex-1 bg-slate-900/60 border border-eoc-border rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200"
                />
              </div>
              <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer border border-dashed border-eoc-border rounded-lg px-3 py-2 hover:bg-slate-800/40">
                <Camera size={14} />
                {photo ? photo.name : 'Attach a photo (JPEG/PNG, max 5 MB)'}
                <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => {
                  const f = e.target.files?.[0]
                  setPhoto(f || null)
                  setPhotoUrl(f ? URL.createObjectURL(f) : '')
                }} />
              </label>
              {photoUrl && <img src={photoUrl} alt="preview" className="rounded-lg max-h-32 object-cover border border-eoc-border" />}
              <button
                onClick={submitReport}
                disabled={busy}
                className="w-full flex items-center justify-center gap-1.5 text-[12px] font-bold bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-lg py-2"
              >
                <Send size={13} /> {busy ? 'Submitting…' : 'Submit report'}
              </button>

              {ticket && (
                <div className="rounded-xl border border-green-500/30 bg-green-500/10 p-3 text-[11px] text-green-200 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <CheckCircle2 size={13} /> Report submitted — ticket {ticket.ticket}
                  </div>
                  <div className="text-green-300/80">
                    Zone: {ticket.zone_name} · Category: {ticket.category} · Status: {ticket.status}
                  </div>
                  <div className="text-[10px] text-green-300/70">
                    Track it later with report id <span className="font-mono">{ticket.report_id}</span>.
                  </div>
                </div>
              )}
            </div>
          )}

          {err && <p className="text-[11px] text-red-400 bg-red-500/10 rounded-lg p-2 mt-3">{err}</p>}
        </div>

        <div className="flex items-center gap-1.5 px-4 py-2.5 border-t border-eoc-border text-[10px] text-slate-500">
          <LifeBuoy size={11} className="text-green-400" />
          Reports feed directly into the situation awareness of the EOC dashboard.
        </div>
      </div>
    </div>
  )
}