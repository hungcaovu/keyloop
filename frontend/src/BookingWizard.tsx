import { useState, useCallback, useEffect } from 'react'
import {
  api,
  Dealership, Customer, Vehicle, ServiceType,
  Technician, CalendarDay, TimeSlot, Appointment,
} from './api'

// ── Step definitions ──────────────────────────────────────────────────────────

type Step =
  | 'dealership'
  | 'customer_search'
  | 'customer_form'
  | 'customer_detail'
  | 'vehicle_select'
  | 'vehicle_detail'
  | 'vehicle_form'
  | 'service_type'
  | 'technician'
  | 'calendar'
  | 'review'
  | 'pending_confirm'
  | 'success'

const STEP_TITLE: Record<Step, string> = {
  dealership:      'Select Dealership',
  customer_search: 'Find Customer',
  customer_form:   'New Customer',
  customer_detail: 'Customer Info',
  vehicle_select:  'Select Vehicle',
  vehicle_detail:  'Vehicle Info',
  vehicle_form:    'Register Vehicle',
  service_type:    'Select Service',
  technician:      'Select Technician',
  calendar:        'Pick a Time',
  review:          'Review & Confirm',
  pending_confirm: 'Confirm Hold',
  success:         'Booking Confirmed',
}

const PROGRESS_STEPS: Step[] = [
  'dealership', 'customer_search', 'vehicle_select',
  'service_type', 'calendar', 'review',
]

const BACK_MAP: Partial<Record<Step, Step>> = {
  customer_search: 'dealership',
  customer_form:   'customer_search',
  customer_detail: 'customer_search',
  vehicle_select:  'customer_detail',
  vehicle_detail:  'vehicle_select',
  vehicle_form:    'vehicle_select',
  service_type:    'vehicle_detail',
  technician:      'service_type',
  calendar:        'service_type',
  review:          'calendar',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: '#16a34a',
  PENDING:   '#d97706',
  COMPLETED: '#2563eb',
  CANCELLED: '#6b7280',
  EXPIRED:   '#9ca3af',
}

function statusBadge(status: string) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: '0.75rem',
      fontWeight: 600, color: '#fff', background: STATUS_COLOR[status] ?? '#6b7280',
    }}>
      {status}
    </span>
  )
}

function fmtDate(iso: string, tz?: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', timeZone: tz,
  })
}

function fmtTime(iso: string, tz?: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: tz })
}

function fmtDateTime(iso: string, tz?: string) {
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long',
    day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: tz,
  })
}

function todayStr() {
  return new Date().toISOString().split('T')[0]
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function BookingWizard() {
  const [step, setStep] = useState<Step>('dealership')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Booking state
  const [dealership, setDealership]     = useState<Dealership | null>(null)
  const [customer, setCustomer]         = useState<Customer | null>(null)
  const [vehicle, setVehicle]           = useState<Vehicle | null>(null)
  const [serviceType, setServiceType]   = useState<ServiceType | null>(null)
  const [technician, setTechnician]     = useState<Technician | null>(null)
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null)
  const [appointment, setAppointment]   = useState<Appointment | null>(null)

  // List data
  const [dealershipResults, setDealershipResults] = useState<Dealership[]>([])
  const [customerResults, setCustomerResults]     = useState<Customer[]>([])
  const [customerVehicles, setCustomerVehicles]   = useState<Vehicle[]>([])
  const [serviceTypes, setServiceTypes]           = useState<ServiceType[]>([])
  const [technicians, setTechnicians]             = useState<Technician[]>([])
  const [calendarDays, setCalendarDays]           = useState<CalendarDay[]>([])
  const [selectedDate, setSelectedDate]           = useState<string | null>(null)

  // Form inputs
  const [dealershipQ, setDealershipQ]   = useState('')
  const [customerQ, setCustomerQ]       = useState('')
  const [technicianQ, setTechnicianQ]     = useState('')
  const [serviceTypeQ, setServiceTypeQ]   = useState('')
  const [customerForm, setCustomerForm] = useState({
    first_name: '', last_name: '', email: '', phone: '',
    address_line1: '', address_line2: '', city: '', state: '', postal_code: '', country: '',
  })
  const [vehicleForm, setVehicleForm]   = useState({ make: '', model: '', year: '', vin: '' })
  const [vinSearchQ, setVinSearchQ]     = useState('')
  const [vinSearchResult, setVinSearchResult] = useState<Vehicle | null | 'not_found'>(null)

  // Edit mode flags
  const [customerEditing, setCustomerEditing] = useState(false)
  const [vehicleEditing, setVehicleEditing]   = useState(false)

  // Countdown for PENDING hold TTL
  const [holdSecondsLeft, setHoldSecondsLeft] = useState<number | null>(null)

  useEffect(() => {
    if (step !== 'pending_confirm' || !appointment?.expires_at) return
    const snap = appointment   // capture for the interval closure
    const tick = () => {
      const diff = Math.floor((new Date(snap.expires_at!).getTime() - Date.now()) / 1000)
      if (diff <= 0) {
        setHoldSecondsLeft(0)
        setError('Hold expired. Please select a new time slot.')
        // Cancel the expired hold — fire-and-forget (backend TTL already excludes it
        // from queries, but we call cancel so the record is marked CANCELLED cleanly)
        console.log('[cancelHold] hold expired — calling cancel API for appointment', snap.id)
        api.cancelAppointment(snap.id).catch(err =>
          console.warn('[cancelHold] cancel on expired hold failed (ignored):', err)
        )
        setAppointment(null)
        setStep('calendar')
      } else {
        setHoldSecondsLeft(diff)
      }
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [step, appointment?.expires_at])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const emptyAddr = { address_line1: '', address_line2: '', city: '', state: '', postal_code: '', country: '' }

  const customerToForm = (c: Customer) => ({
    first_name:    c.first_name,
    last_name:     c.last_name,
    email:         c.email,
    phone:         c.phone         ?? '',
    address_line1: c.address_line1 ?? '',
    address_line2: c.address_line2 ?? '',
    city:          c.city          ?? '',
    state:         c.state         ?? '',
    postal_code:   c.postal_code   ?? '',
    country:       c.country       ?? '',
  })

  // ── Actions ─────────────────────────────────────────────────────────────────

  const run = useCallback(async (fn: () => Promise<void>) => {
    setLoading(true)
    setError(null)
    try {
      await fn()
    } catch (e: unknown) {
      const msg = (e as { error?: string; message?: string })?.error
        || (e as { message?: string })?.message
        || 'Something went wrong'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  // STEP 0 — load all dealerships on mount
  useEffect(() => {
    run(async () => {
      const res = await api.listDealerships()
      setDealershipResults(res.data)
    })
  }, [run])

  const searchDealerships = () => run(async () => {
    const res = dealershipQ.length >= 2
      ? await api.searchDealerships(dealershipQ)
      : await api.listDealerships()
    setDealershipResults(res.data)
  })

  const pickDealership = (d: Dealership) => {
    setDealership(d)
    // Clear all downstream state so summary bar never shows stale customer/vehicle
    setCustomer(null); setCustomerVehicles([]); setVehicle(null)
    setServiceType(null); setTechnician(null); setSelectedSlot(null)
    setCustomerResults([])
    setCustomerQ('')
    setStep('customer_search')
  }

  // STEP 0a — auto-search as user types (debounced, no global loading spinner)
  useEffect(() => {
    if (step !== 'customer_search') return
    if (customerQ.length < 2) { setCustomerResults([]); return }
    const timer = setTimeout(() => {
      api.searchCustomers(customerQ)
        .then(res => setCustomerResults(res.data))
        .catch(() => {/* ignore mid-type errors */})
    }, 300)
    return () => clearTimeout(timer)
  }, [customerQ, step])  // eslint-disable-line react-hooks/exhaustive-deps

  const searchCustomer = () => run(async () => {
    if (!customerQ || customerQ.length < 2) { setError('Enter at least 2 characters'); return }
    const res = await api.searchCustomers(customerQ)
    setCustomerResults(res.data)
  })

  const pickCustomer = (c: Customer) => run(async () => {
    const res = await api.getCustomerWithVehicles(c.id)
    const loaded = res.customer
    setCustomer(loaded)
    setCustomerVehicles(loaded.vehicles ?? [])
    setCustomerForm(customerToForm(loaded))
    setCustomerEditing(false)
    setVehicle(null)
    setStep('customer_detail')
  })

  const goToCustomerForm = () => {
    // pre-fill phone if the query looks like a phone number, else leave blank
    const looksLikePhone = /^[+\d\s()-]{7,}$/.test(customerQ)
    setCustomerForm({ ...emptyAddr, first_name: '', last_name: '', email: '', phone: looksLikePhone ? customerQ : '' })
    setStep('customer_form')
  }

  const createCustomer = () => run(async () => {
    const { first_name, last_name, email, phone, address_line1, address_line2, city, state, postal_code, country } = customerForm
    if (!first_name || !last_name || !email) { setError('First name, last name and email are required'); return }
    const res = await api.createCustomer({
      first_name, last_name, email,
      phone: phone || undefined,
      address_line1: address_line1 || undefined,
      address_line2: address_line2 || undefined,
      city: city || undefined,
      state: state || undefined,
      postal_code: postal_code || undefined,
      country: country || undefined,
    })
    setCustomer(res.customer)
    setCustomerVehicles([])
    setStep('vehicle_select')
  })

  const saveCustomer = () => run(async () => {
    const { first_name, last_name, email, phone, address_line1, address_line2, city, state, postal_code, country } = customerForm
    if (!first_name || !last_name || !email) { setError('First name, last name and email are required'); return }
    const res = await api.updateCustomer(customer!.id, {
      first_name, last_name, email,
      phone: phone || null,
      address_line1: address_line1 || null,
      address_line2: address_line2 || null,
      city: city || null,
      state: state || null,
      postal_code: postal_code || null,
      country: country || null,
    })
    setCustomer(res.customer)
    setCustomerEditing(false)
  })

  // STEP 0b
  const pickVehicle = (v: Vehicle) => {
    setVehicle(v)
    setVehicleForm({
      make:  v.make,
      model: v.model,
      year:  String(v.year),
      vin:   v.vin ?? '',
    })
    setVehicleEditing(false)
    setVinSearchQ('')
    setVinSearchResult(null)
    setStep('vehicle_detail')
  }

  const searchVehicleByVin = () => run(async () => {
    const q = vinSearchQ.trim()
    if (!q) { setError('Enter a VIN or vehicle ref'); return }
    try {
      const res = await api.lookupVehicle(q)
      setVinSearchResult(res.vehicle)
    } catch {
      setVinSearchResult('not_found')
    }
  })

  const continueWithVehicle = () => run(async () => {
    await loadServiceTypes()
  })

  const loadServiceTypes = async () => {
    const res = await api.listServiceTypes()
    setServiceTypes(res.data)
    setStep('service_type')
  }

  const createVehicle = () => run(async () => {
    const { make, model, year, vin } = vehicleForm
    if (!make || !model || !year) { setError('Make, model and year are required'); return }
    const res = await api.createVehicle({
      customer_id: customer!.id,
      make, model,
      year: parseInt(year),
      vin: vin || undefined,
    })
    setVehicle(res.vehicle)
    await loadServiceTypes()
  })

  const saveVehicle = () => run(async () => {
    const { make, model, year, vin } = vehicleForm
    if (!make || !model || !year) { setError('Make, model and year are required'); return }
    const res = await api.updateVehicle(vehicle!.id, {
      make, model,
      year: parseInt(year),
      vin: vin || null,
    })
    setVehicle(res.vehicle)
    setVehicleEditing(false)
  })

  // STEP 0c
  const pickServiceType = (st: ServiceType) => run(async () => {
    setServiceType(st)
    setTechnician(null)
    setTechnicianQ('')
    const res = await api.listTechnicians(dealership!.id, st.id)
    setTechnicians(res.data)
    setStep('technician')
  })

  // STEP 0c.5
  const pickTechnician = (t: Technician | null) => run(async () => {
    setTechnician(t)
    await loadCalendar(t?.id)
  })

  // STEP 0d
  const loadCalendar = async (technicianId?: string | number, fromDate?: string) => {
    const from = fromDate ?? todayStr()
    const res = await api.getCalendarSlots(dealership!.id, serviceType!.id, from, technicianId != null ? String(technicianId) : undefined)
    const slots = res.slots ?? []
    setCalendarDays(slots)
    const firstAvailable = slots.find(d => d.available_times.length > 0)
    setSelectedDate(firstAvailable?.date ?? null)
    setStep('calendar')
  }

  const pickSlot = (slot: TimeSlot) => {
    setSelectedSlot(slot)
    setError(null)
    setStep('review')
  }

  // STEP 1 — create PENDING hold
  const confirmBooking = () => run(async () => {
    try {
      const res = await api.createAppointment({
        dealership_id:   dealership!.id,
        customer_id:     customer!.id,
        vehicle_id:      vehicle!.id,
        service_type_id: serviceType!.id,
        desired_start:   selectedSlot!.start,
        technician_id:   technician?.id,
      })
      setAppointment(res.appointment)
      setStep('pending_confirm')
    } catch (e: unknown) {
      const err = e as { error?: string; message?: string; next_available_slot?: string }
      if (err.next_available_slot) {
        const fromDate = err.next_available_slot.split('T')[0]
        setSelectedSlot(null)
        setError('That time slot was just taken. Please choose another.')
        await loadCalendar(technician?.id, fromDate)
      } else {
        throw e
      }
    }
  })

  // STEP 1b — confirm PENDING → CONFIRMED
  const confirmPendingBooking = () => run(async () => {
    try {
      const res = await api.confirmAppointment(appointment!.id)
      setAppointment(res.appointment)
      setStep('success')
    } catch (e: unknown) {
      const err = e as { error?: string; message?: string; next_available_slot?: string }
      if (err.next_available_slot) {
        const fromDate = err.next_available_slot.split('T')[0]
        setAppointment(null)
        setSelectedSlot(null)
        setError('Hold expired — the slot is no longer held. Please choose another time.')
        await loadCalendar(technician?.id, fromDate)
      } else {
        throw e
      }
    }
  })

  // Cancel hold and return to calendar (reload slots to reflect current holds)
  const cancelHold = () => run(async () => {
    if (appointment) {
      console.log('[cancelHold] calling cancel API for appointment', appointment.id)
      try {
        await api.cancelAppointment(appointment.id)
        console.log('[cancelHold] cancel API succeeded')
      } catch (err) {
        console.warn('[cancelHold] cancel API failed (proceeding anyway):', err)
      }
    } else {
      console.warn('[cancelHold] appointment is null — cancel API skipped')
    }
    setAppointment(null)
    await loadCalendar(technician?.id)
  })

  const resetFlow = () => {
    setStep('dealership')
    setDealership(null); setCustomer(null); setVehicle(null)
    setServiceType(null); setTechnician(null); setSelectedSlot(null); setAppointment(null)
    setDealershipQ(''); setCustomerQ(''); setTechnicianQ(''); setServiceTypeQ('')
    setDealershipResults([]); setCustomerResults([])
    setCalendarDays([]); setSelectedDate(null)
    setCustomerEditing(false); setVehicleEditing(false)
  }

  const goBack = () => {
    if (step === 'pending_confirm') { cancelHold(); return }
    if (step === 'review') { run(async () => { await loadCalendar(technician?.id) }); return }
    const prev = BACK_MAP[step]
    if (!prev) return

    // When navigating back, clear state that belongs to steps after the target.
    // This prevents stale vehicle / service-type / technician data from showing
    // in the summary bar on earlier steps.
    if (['dealership', 'customer_search', 'customer_form'].includes(prev)) {
      setCustomer(null); setCustomerVehicles([]); setVehicle(null)
      setServiceType(null); setTechnician(null); setSelectedSlot(null)
    } else if (['customer_detail', 'vehicle_select', 'vehicle_form'].includes(prev)) {
      setVehicle(null); setServiceType(null); setTechnician(null); setSelectedSlot(null)
    } else if (['vehicle_detail', 'service_type'].includes(prev)) {
      setServiceType(null); setTechnician(null); setSelectedSlot(null)
    } else if (['technician', 'calendar'].includes(prev)) {
      setSelectedSlot(null)
    }

    setStep(prev)
  }

  // ── Summary bar ──────────────────────────────────────────────────────────────

  const renderSummary = () => {
    const items: { icon: string; label: string; lines: string[] }[] = []

    if (dealership)
      items.push({ icon: '📍', label: 'Dealership', lines: [dealership.name] })
    if (customer) {
      const sub = [customer.phone, customer.email, customer.city].filter(Boolean).join(' · ')
      items.push({ icon: '👤', label: 'Customer', lines: [`${customer.first_name} ${customer.last_name}`, sub] })
    }
    if (vehicle)
      items.push({ icon: '🚗', label: 'Vehicle', lines: [`${vehicle.year} ${vehicle.make} ${vehicle.model}`] })
    if (serviceType)
      items.push({ icon: '🔧', label: 'Service', lines: [`${serviceType.name} (${serviceType.duration_minutes} min)`] })
    if (technician)
      items.push({ icon: '👷', label: 'Technician', lines: [`${technician.first_name} ${technician.last_name}`] })
    if (selectedSlot)
      items.push({ icon: '🗓️', label: 'Time', lines: [fmtDateTime(selectedSlot.start, dealership?.timezone)] })

    if (items.length === 0) return null

    return (
      <div className="summary-bar">
        {items.map(it => (
          <div key={it.label} className="summary-row">
            <span className="summary-icon">{it.icon}</span>
            <span className="summary-label">{it.label}</span>
            <span className="summary-value">
              {it.lines[0]}
              {it.lines[1] && <span className="summary-sub">{it.lines[1]}</span>}
            </span>
          </div>
        ))}
      </div>
    )
  }

  // ── Renders ──────────────────────────────────────────────────────────────────

  const renderDealership = () => (
    <div>
      <div className="search-row">
        <input
          className="input"
          placeholder="Search dealership (e.g. Metro Honda)"
          value={dealershipQ}
          onChange={e => setDealershipQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && searchDealerships()}
        />
        <button className="btn" onClick={searchDealerships}>Search</button>
      </div>
      {dealershipResults.length === 0 && dealershipQ.length >= 2 && !loading && (
        <p className="hint">No results. Try a different name.</p>
      )}
      {dealershipResults.map(d => (
        <button key={d.id} className="card card-btn" onClick={() => pickDealership(d)}>
          <span className="card-title">{d.name}</span>
          <span className="card-sub">{d.city}, {d.state} · {d.timezone}</span>
        </button>
      ))}
    </div>
  )

  const renderCustomerSearch = () => (
    <div>
      <button className="btn btn-outline" style={{ marginBottom: 12 }} onClick={goToCustomerForm}>
        + Register New Customer
      </button>
      <div className="search-row">
        <input
          className="input"
          placeholder="Search by name or phone (e.g. Smith, +1-555-0101)"
          value={customerQ}
          onChange={e => setCustomerQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && searchCustomer()}
        />
        <button className="btn" onClick={searchCustomer}>Search</button>
      </div>
      {customerResults.map(c => {
        const addressParts = [c.address_line1, c.address_line2, c.city, c.state, c.postal_code, c.country].filter(Boolean)
        return (
          <button key={c.id} className="card card-btn" onClick={() => pickCustomer(c)}>
            <span className="card-title">{c.first_name} {c.last_name}</span>
            <span className="card-sub">{c.email}{c.phone ? ` · ${c.phone}` : ''}</span>
            <span className="card-sub">{addressParts.length > 0 ? addressParts.join(', ') : '—'}</span>
          </button>
        )
      })}
      {customerResults.length === 0 && customerQ.length >= 2 && !loading && (
        <p className="hint">No customer found.</p>
      )}
    </div>
  )

  const CUSTOMER_FIELDS = [
    { key: 'first_name',    label: 'First Name *',    type: 'text'  },
    { key: 'last_name',     label: 'Last Name *',     type: 'text'  },
    { key: 'email',         label: 'Email *',         type: 'email' },
    { key: 'phone',         label: 'Phone',           type: 'tel'   },
    { key: 'address_line1', label: 'Address Line 1',  type: 'text'  },
    { key: 'address_line2', label: 'Address Line 2',  type: 'text'  },
    { key: 'city',          label: 'City',            type: 'text'  },
    { key: 'state',         label: 'State',           type: 'text'  },
    { key: 'postal_code',   label: 'Postal Code',     type: 'text'  },
    { key: 'country',       label: 'Country',         type: 'text'  },
  ] as const

  const renderCustomerFields = (readonly: boolean) => (
    <>
      <div className="field-row">
        {(['first_name', 'last_name'] as const).map(key => (
          <div key={key} className="field">
            <label className="label">{key === 'first_name' ? 'First Name *' : 'Last Name *'}</label>
            {readonly ? (
              <div className="field-readonly">{customerForm[key] || '—'}</div>
            ) : (
              <input className="input" type="text" value={customerForm[key]}
                onChange={e => setCustomerForm(f => ({ ...f, [key]: e.target.value }))} />
            )}
          </div>
        ))}
      </div>
      <div className="field-row">
        {(['email', 'phone'] as const).map(key => (
          <div key={key} className="field">
            <label className="label">{key === 'email' ? 'Email *' : 'Phone'}</label>
            {readonly ? (
              <div className="field-readonly">{customerForm[key] || '—'}</div>
            ) : (
              <input className="input" type={key === 'email' ? 'email' : 'tel'} value={customerForm[key]}
                onChange={e => setCustomerForm(f => ({ ...f, [key]: e.target.value }))} />
            )}
          </div>
        ))}
      </div>
      {CUSTOMER_FIELDS.filter(f => !['first_name', 'last_name', 'email', 'phone', 'city', 'state', 'postal_code', 'country'].includes(f.key)).map(({ key, label, type }) => (
        <div key={key} className="field">
          <label className="label">{label}</label>
          {readonly ? (
            <div className="field-readonly">{customerForm[key] || '—'}</div>
          ) : (
            <input className="input" type={type} value={customerForm[key]}
              onChange={e => setCustomerForm(f => ({ ...f, [key]: e.target.value }))} />
          )}
        </div>
      ))}
      <div className="field-row">
        {(['city', 'state'] as const).map(key => (
          <div key={key} className="field">
            <label className="label">{key === 'city' ? 'City' : 'State'}</label>
            {readonly ? (
              <div className="field-readonly">{customerForm[key] || '—'}</div>
            ) : (
              <input className="input" type="text" value={customerForm[key]}
                onChange={e => setCustomerForm(f => ({ ...f, [key]: e.target.value }))} />
            )}
          </div>
        ))}
      </div>
      <div className="field-row">
        {(['postal_code', 'country'] as const).map(key => (
          <div key={key} className="field">
            <label className="label">{key === 'postal_code' ? 'Postal Code' : 'Country'}</label>
            {readonly ? (
              <div className="field-readonly">{customerForm[key] || '—'}</div>
            ) : (
              <input className="input" type="text" value={customerForm[key]}
                onChange={e => setCustomerForm(f => ({ ...f, [key]: e.target.value }))} />
            )}
          </div>
        ))}
      </div>
    </>
  )

  const renderCustomerForm = () => (
    <div>
      {renderCustomerFields(false)}
      <button className="btn" style={{ marginTop: 16, width: '100%' }} onClick={createCustomer}>
        Create Customer
      </button>
    </div>
  )

  const renderCustomerDetail = () => (
    <div>
      <div className="detail-header">
        <span className="detail-badge">👤 Customer</span>
        {!customerEditing && (
          <button className="btn-icon" onClick={() => setCustomerEditing(true)}>✏️ Edit</button>
        )}
      </div>
      {renderCustomerFields(!customerEditing)}
      {customerEditing ? (
        <div className="action-row">
          <button className="btn btn-outline" onClick={() => {
            setCustomerForm(customerToForm(customer!))
            setCustomerEditing(false)
          }}>
            Cancel
          </button>
          <button className="btn" onClick={saveCustomer}>Save Changes</button>
        </div>
      ) : (
        <button className="btn btn-green" style={{ marginTop: 16, width: '100%' }}
          onClick={() => setStep('vehicle_select')}>
          Continue →
        </button>
      )}
    </div>
  )

  const renderVehicleSelect = () => (
    <div>
      {/* VIN / vehicle-ref search */}
      <p className="section-label">Search vehicle in database</p>
      <div className="search-row">
        <input
          className="input"
          placeholder="VIN or vehicle ref (e.g. 1HGCM82633A123456, VH-000012)"
          value={vinSearchQ}
          onChange={e => { setVinSearchQ(e.target.value); setVinSearchResult(null) }}
          onKeyDown={e => e.key === 'Enter' && searchVehicleByVin()}
        />
        <button className="btn" onClick={searchVehicleByVin}>Search</button>
      </div>

      {vinSearchResult === 'not_found' && (
        <div style={{ margin: '8px 0 4px', padding: '10px 12px', background: '#fef9c3', borderRadius: 8, border: '1px solid #fde047', fontSize: '0.875rem', color: '#92400e' }}>
          Vehicle not found.{' '}
          <button className="link-btn" onClick={() => {
            setVinSearchQ('')
            setVinSearchResult(null)
            setVehicleForm({ make: '', model: '', year: '', vin: vinSearchQ })
            setStep('vehicle_form')
          }}>Register as new vehicle →</button>
        </div>
      )}

      {vinSearchResult && vinSearchResult !== 'not_found' && (
        <>
          <p className="section-label">Found in database</p>
          <button className="card card-btn" style={{ borderColor: '#2563eb' }} onClick={() => pickVehicle(vinSearchResult as Vehicle)}>
            <span className="card-title">{(vinSearchResult as Vehicle).year} {(vinSearchResult as Vehicle).make} {(vinSearchResult as Vehicle).model}</span>
            <span className="card-sub">{(vinSearchResult as Vehicle).vin ?? (vinSearchResult as Vehicle).vehicle_ref ?? 'No VIN'}</span>
          </button>
        </>
      )}

      <div style={{ margin: '16px 0 8px', borderTop: '1px solid #e2e8f0' }} />

      {/* Customer's existing vehicles */}
      {customerVehicles.length === 0 && !vinSearchResult && (
        <p className="hint">No vehicles registered for this customer yet.</p>
      )}
      {customerVehicles.length > 0 && (
        <>
          <p className="section-label">Customer's vehicles</p>
          {customerVehicles.map(v => (
            <button key={v.id} className="card card-btn" onClick={() => pickVehicle(v)}>
              <span className="card-title">{v.year} {v.make} {v.model}</span>
              <span className="card-sub">{v.vin ?? v.vehicle_ref ?? 'No VIN'}</span>
            </button>
          ))}
        </>
      )}

      <button className="btn btn-outline" style={{ marginTop: 8, width: '100%' }} onClick={() => {
        setVehicleForm({ make: '', model: '', year: '', vin: '' })
        setVinSearchQ('')
        setVinSearchResult(null)
        setStep('vehicle_form')
      }}>
        + Register New Vehicle
      </button>
    </div>
  )

  const VEHICLE_FIELDS = [
    { key: 'make',  label: 'Make',           type: 'text'   },
    { key: 'model', label: 'Model',          type: 'text'   },
    { key: 'year',  label: 'Year',           type: 'number' },
    { key: 'vin',   label: 'VIN (optional)', type: 'text'   },
  ] as const

  const renderVehicleDetail = () => (
    <div>
      <div className="detail-header">
        <span className="detail-badge">🚗 Vehicle</span>
        {!vehicleEditing && (
          <button className="btn-icon" onClick={() => setVehicleEditing(true)}>✏️ Edit</button>
        )}
      </div>
      {VEHICLE_FIELDS.map(({ key, label, type }) => (
        <div key={key} className="field">
          <label className="label">{label}</label>
          {vehicleEditing ? (
            <input
              className="input"
              type={type}
              value={vehicleForm[key]}
              onChange={e => setVehicleForm(f => ({ ...f, [key]: e.target.value }))}
            />
          ) : (
            <div className="field-readonly">{vehicleForm[key] || '—'}</div>
          )}
        </div>
      ))}
      {/* Recent appointments */}
      {vehicle?.recent_appointments !== undefined && (
        <div style={{ marginTop: 16, padding: '12px 14px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', marginBottom: 8 }}>
            LAST {vehicle.recent_appointments.length > 0 ? vehicle.recent_appointments.length : ''} APPOINTMENT{vehicle.recent_appointments.length !== 1 ? 'S' : ''}
          </div>
          {vehicle.recent_appointments.length === 0 ? (
            <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>No previous appointments</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {vehicle.recent_appointments.map((appt, i) => (
                <div key={appt.id} style={{
                  display: 'flex', flexDirection: 'column', gap: 3,
                  paddingBottom: i < vehicle.recent_appointments!.length - 1 ? 10 : 0,
                  borderBottom: i < vehicle.recent_appointments!.length - 1 ? '1px solid #e2e8f0' : 'none',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {statusBadge(appt.status)}
                    <span style={{ fontWeight: 500 }}>{appt.service_type.name}</span>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#475569' }}>
                    {fmtDateTime(appt.scheduled_start, dealership?.timezone)}
                  </div>
                  {appt.technician && (
                    <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                      👷 {appt.technician.name}
                    </div>
                  )}
                  {appt.booked_by && (
                    <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                      📋 Booked by {appt.booked_by.name}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {vehicleEditing ? (
        <div className="action-row">
          <button className="btn btn-outline" onClick={() => {
            setVehicleForm({ make: vehicle!.make, model: vehicle!.model, year: String(vehicle!.year), vin: vehicle!.vin ?? '' })
            setVehicleEditing(false)
          }}>
            Cancel
          </button>
          <button className="btn" onClick={saveVehicle}>Save Changes</button>
        </div>
      ) : (
        <button className="btn btn-green" style={{ marginTop: 16, width: '100%' }}
          onClick={continueWithVehicle}>
          Continue →
        </button>
      )}
    </div>
  )

  const renderVehicleForm = () => (
    <div>
      {VEHICLE_FIELDS.map(({ key, label, type }) => (
        <div key={key} className="field">
          <label className="label">{label} {key !== 'vin' ? '*' : ''}</label>
          <input
            className="input"
            type={type}
            value={vehicleForm[key]}
            onChange={e => setVehicleForm(f => ({ ...f, [key]: e.target.value }))}
          />
        </div>
      ))}
      <button className="btn" style={{ marginTop: 16, width: '100%' }} onClick={createVehicle}>
        Register Vehicle
      </button>
    </div>
  )

  const renderServiceType = () => {
    const filtered = serviceTypeQ
      ? serviceTypes.filter(st => st.name.toLowerCase().includes(serviceTypeQ.toLowerCase()))
      : serviceTypes
    return (
      <div>
        <input
          className="input"
          placeholder="Search service (e.g. Oil Change)"
          value={serviceTypeQ}
          onChange={e => setServiceTypeQ(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        {filtered.map(st => (
          <button key={st.id} className="card card-btn" onClick={() => pickServiceType(st)}>
            <span className="card-title">{st.name}</span>
            <span className="card-sub">{st.duration_minutes} min · Bay: {st.bay_type}</span>
          </button>
        ))}
        {filtered.length === 0 && serviceTypeQ && (
          <p className="hint">No service found for "{serviceTypeQ}".</p>
        )}
      </div>
    )
  }

  const renderTechnician = () => {
    const filtered = technicianQ
      ? technicians.filter(t =>
          `${t.first_name} ${t.last_name}`.toLowerCase().includes(technicianQ.toLowerCase())
        )
      : technicians
    return (
      <div>
        <input
          className="input"
          placeholder="Search technician by name..."
          value={technicianQ}
          onChange={e => setTechnicianQ(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <button className="card card-btn" style={{ borderStyle: 'dashed' }} onClick={() => pickTechnician(null)}>
          <span className="card-title">Auto-assign</span>
          <span className="card-sub">System picks the least-loaded available technician</span>
        </button>
        {filtered.map(t => (
          <button key={t.id} className="card card-btn" onClick={() => pickTechnician(t)}>
            <span className="card-title">{t.first_name} {t.last_name}</span>
            <span className="card-sub">{t.employee_number}</span>
          </button>
        ))}
        {filtered.length === 0 && technicianQ && (
          <p className="hint">No technician found for "{technicianQ}".</p>
        )}
      </div>
    )
  }

  const renderCalendar = () => {
    const activeDays = calendarDays.filter(d => d.available_times.length > 0)
    const slots = selectedDate
      ? calendarDays.find(d => d.date === selectedDate)?.available_times ?? []
      : []

    return (
      <div>
        {activeDays.length === 0 && (
          <p className="hint">No available slots in the next 14 days.</p>
        )}
        <div className="date-pills">
          {activeDays.map(d => (
            <button
              key={d.date}
              className={`date-pill${selectedDate === d.date ? ' active' : ''}`}
              onClick={() => setSelectedDate(d.date)}
            >
              <span className="date-pill-main">{fmtDate(d.date, dealership?.timezone)}</span>
              <span className="date-pill-sub">{d.available_times.length} slots</span>
            </button>
          ))}
        </div>
        {selectedDate && (
          <div className="slot-grid">
            {slots.map((slot, i) => (
              <button key={i} className="slot-btn" onClick={() => pickSlot(slot)}>
                <span className="slot-time">{fmtTime(slot.start, dealership?.timezone)} – {fmtTime(slot.end, dealership?.timezone)}</span>
                <span className="slot-techs">{slot.technician_count} tech{slot.technician_count !== 1 ? 's' : ''} · {slot.bay_count} bay{slot.bay_count !== 1 ? 's' : ''}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  const renderReview = () => (
    <div>
      <div className="review-table">
        {[
          ['Dealership', dealership?.name],
          ['Customer',   `${customer?.first_name} ${customer?.last_name} · ${customer?.email}`],
          ['Vehicle',    `${vehicle?.year} ${vehicle?.make} ${vehicle?.model}${vehicle?.vin ? ` (${vehicle.vin})` : ''}`],
          ['Service',    `${serviceType?.name} (${serviceType?.duration_minutes} min)`],
          ['Technician', technician ? `${technician.first_name} ${technician.last_name}` : 'Auto-assign'],
          ['Date & Time', selectedSlot ? fmtDateTime(selectedSlot.start, dealership?.timezone) : ''],
        ].map(([label, value]) => (
          <div key={label} className="review-row">
            <span className="review-label">{label}</span>
            <span className="review-value">{value}</span>
          </div>
        ))}
      </div>
      <button className="btn btn-green" style={{ marginTop: 24, width: '100%' }} onClick={confirmBooking}>
        Confirm Appointment
      </button>
    </div>
  )

  const renderPendingConfirm = () => {
    const mm = holdSecondsLeft != null ? String(Math.floor(holdSecondsLeft / 60)).padStart(2, '0') : '--'
    const ss = holdSecondsLeft != null ? String(holdSecondsLeft % 60).padStart(2, '0') : '--'
    return (
      <div>
        <div className="review-table">
          {[
            ['Dealership', dealership?.name],
            ['Customer',   `${customer?.first_name} ${customer?.last_name} · ${customer?.email}`],
            ['Vehicle',    `${vehicle?.year} ${vehicle?.make} ${vehicle?.model}${vehicle?.vin ? ` (${vehicle.vin})` : ''}`],
            ['Service',    `${serviceType?.name} (${serviceType?.duration_minutes} min)`],
            ['Technician', appointment?.technician?.name ?? 'Auto-assigned'],
            ['Bay',        appointment?.service_bay ? `${appointment.service_bay.bay_number} (${appointment.service_bay.bay_type})` : '—'],
            ['Date & Time', appointment?.scheduled_start ? fmtDateTime(appointment.scheduled_start, dealership?.timezone) : ''],
          ].map(([label, value]) => (
            <div key={label} className="review-row">
              <span className="review-label">{label}</span>
              <span className="review-value">{value}</span>
            </div>
          ))}
        </div>
        <div style={{ textAlign: 'center', margin: '20px 0', fontSize: '1.1rem' }}>
          ⏱ Slot held for <strong>{mm}:{ss}</strong>
        </div>
        <div className="action-row">
          <button className="btn btn-outline" onClick={cancelHold}>Cancel Hold</button>
          <button className="btn btn-green" onClick={confirmPendingBooking}>Confirm Booking</button>
        </div>
      </div>
    )
  }

  const renderSuccess = () => (
    <div className="success-box">
      <div className="success-icon">✓</div>
      <h2 className="success-title">Appointment Confirmed</h2>
      <p className="success-id">ID: {appointment?.id}</p>
      <div className="success-details">
        <p><strong>{appointment?.service_type.name}</strong></p>
        <p>{appointment?.scheduled_start ? fmtDateTime(appointment.scheduled_start, dealership?.timezone) : ''}</p>
        <p>📍 {appointment?.dealership.name}</p>
        <p>👤 {appointment?.customer.name}</p>
        <p>🚗 {appointment?.vehicle.year} {appointment?.vehicle.make} {appointment?.vehicle.model}</p>
        {appointment?.technician && <p>👷 {appointment.technician.name}</p>}
        {appointment?.service_bay && (
          <p>🔲 {appointment.service_bay.bay_number} ({appointment.service_bay.bay_type})</p>
        )}
      </div>
      <button className="btn" style={{ marginTop: 32 }} onClick={resetFlow}>Book Another</button>
    </div>
  )

  const stepContent: Record<Step, () => JSX.Element> = {
    dealership:      renderDealership,
    customer_search: renderCustomerSearch,
    customer_form:   renderCustomerForm,
    customer_detail: renderCustomerDetail,
    vehicle_select:  renderVehicleSelect,
    vehicle_detail:  renderVehicleDetail,
    vehicle_form:    renderVehicleForm,
    service_type:    renderServiceType,
    technician:      renderTechnician,
    calendar:        renderCalendar,
    review:          renderReview,
    pending_confirm: renderPendingConfirm,
    success:         renderSuccess,
  }

  const progressIdx = PROGRESS_STEPS.indexOf(step)

  return (
    <div className="wizard">
      <header className="wizard-header">
        <span className="wizard-logo">🔧 Service Scheduler</span>
        {step !== 'dealership' && step !== 'success' && (
          <button className="back-btn" onClick={goBack}>← Back</button>
        )}
      </header>

      {progressIdx >= 0 && (
        <div className="progress-bar">
          {PROGRESS_STEPS.map((_, i) => (
            <div key={i} className={`progress-dot${i <= progressIdx ? ' active' : ''}`} />
          ))}
        </div>
      )}

      <div className="step-header">
        <h1 className="step-title">{STEP_TITLE[step]}</h1>
      </div>

      {step !== 'dealership' && step !== 'success' && renderSummary()}

      {error && (
        <div className="error-banner" onClick={() => setError(null)}>
          ⚠️ {error} <span className="error-dismiss">×</span>
        </div>
      )}

      <main className="wizard-body">
        {loading
          ? <div className="spinner-wrap"><div className="spinner" /></div>
          : stepContent[step]?.()
        }
      </main>
    </div>
  )
}
