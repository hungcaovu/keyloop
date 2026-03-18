const BASE = '/api'

function generateRequestId(): string {
  const ts  = Date.now().toString(36)
  const rnd = Math.random().toString(36).slice(2, 7)
  return `${ts}-${rnd}`
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url       = `${BASE}${path}`
  const requestId = generateRequestId()

  console.group(`%c${method} ${path}`, 'color: #2563eb; font-weight: bold')
  console.log('request_id:', requestId)
  if (body) console.log('request body:', body)

  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()

  if (!res.ok) {
    console.error(`%c${res.status} ERROR`, 'color: #dc2626; font-weight: bold', data)
    console.groupEnd()
    throw data
  }

  console.log(`%c${res.status} OK`, 'color: #16a34a; font-weight: bold', data)
  console.groupEnd()
  return data
}

const get   = <T>(path: string)                  => req<T>('GET',   path)
const post  = <T>(path: string, body: unknown)   => req<T>('POST',  path, body)
const patch = <T>(path: string, body: unknown)   => req<T>('PATCH', path, body)

// ── Types ────────────────────────────────────────────────────────────────────

export interface Dealership {
  id: string
  name: string
  city: string
  state: string
  timezone: string
}

export interface Customer {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string | null
  address_line1: string | null
  address_line2: string | null
  city: string | null
  state: string | null
  postal_code: string | null
  country: string | null
  vehicles?: Vehicle[]
}

export interface RecentAppointment {
  id: number
  status: string
  scheduled_start: string
  scheduled_end: string
  service_type: { name: string }
  technician: { id: string; name: string } | null
  booked_by: { id: string; name: string } | null
}

export interface Vehicle {
  id: string
  make: string
  model: string
  year: number
  vin: string | null
  vehicle_ref: string | null
  customer_id: string
  recent_appointments?: RecentAppointment[]
}

export interface ServiceType {
  id: string
  name: string
  duration_minutes: number
  bay_type: string
}

export interface Technician {
  id: string
  first_name: string
  last_name: string
  employee_number: string
}

export interface TimeSlot {
  start: string
  end: string
  technician_count: number
  bay_count: number
}

export interface CalendarDay {
  date: string
  available_times: TimeSlot[]
}

export interface Appointment {
  id: string
  status: string
  scheduled_start: string
  scheduled_end: string
  expires_at: string | null
  customer: { id: string; name: string }
  vehicle: { id: string; make: string; model: string; year: number }
  dealership: { id: string; name: string }
  service_type: { id: string; name: string; duration_minutes: number }
  technician: { id: string; name: string } | null
  service_bay: { id: string; bay_number: string; bay_type: string } | null
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  // STEP 0 — dealerships
  listDealerships: () =>
    get<{ data: Dealership[]; next_cursor: string | null }>('/dealerships?limit=10'),

  searchDealerships: (q: string) =>
    get<{ data: Dealership[]; next_cursor: string | null }>(`/dealerships?q=${encodeURIComponent(q)}&limit=10`),

  // STEP 0a — customers
  searchCustomers: (q: string) =>
    get<{ data: Customer[]; next_cursor: string | null }>(`/customers?q=${encodeURIComponent(q)}&limit=10`),

  searchCustomerByPhone: (phone: string) =>
    get<{ data: Customer[] }>(`/customers?phone=${encodeURIComponent(phone)}`),

  createCustomer: (body: {
    first_name: string; last_name: string; email: string; phone?: string;
    address_line1?: string; address_line2?: string; city?: string;
    state?: string; postal_code?: string; country?: string;
  }) =>
    post<{ customer: Customer; warning?: unknown }>('/customers', body),

  getCustomerWithVehicles: (id: string) =>
    get<{ customer: Customer }>(`/customers/${id}?include=vehicles`),

  // STEP 0a — update customer
  updateCustomer: (id: string, body: Partial<{
    first_name: string; last_name: string; email: string; phone: string | null;
    address_line1: string | null; address_line2: string | null; city: string | null;
    state: string | null; postal_code: string | null; country: string | null;
  }>) =>
    patch<{ customer: Customer }>(`/customers/${id}`, body),

  // STEP 0b — vehicles
  lookupVehicle: (identifier: string) =>
    get<{ vehicle: Vehicle }>(`/vehicles/${encodeURIComponent(identifier)}`),

  createVehicle: (body: { customer_id: string; make: string; model: string; year: number; vin?: string }) =>
    post<{ vehicle: Vehicle }>('/vehicles', body),

  updateVehicle: (id: string, body: Partial<{ make: string; model: string; year: number; vin: string | null }>) =>
    patch<{ vehicle: Vehicle }>(`/vehicles/${id}`, body),

  // STEP 0c — service types
  listServiceTypes: () =>
    get<{ data: ServiceType[] }>('/service-types'),

  searchServiceTypes: (q: string) =>
    get<{ data: ServiceType[] }>(`/service-types?q=${encodeURIComponent(q)}`),

  // STEP 0c.5 — technicians
  listTechnicians: (dealershipId: string, serviceTypeId: string) =>
    get<{ data: Technician[] }>(`/dealerships/${dealershipId}/technicians?service_type_id=${serviceTypeId}`),

  // STEP 0d — calendar
  getCalendarSlots: (dealershipId: string, serviceTypeId: string, fromDate: string, technicianId?: string) => {
    const params = new URLSearchParams({ service_type_id: serviceTypeId, from_date: fromDate, days: '14' })
    if (technicianId) params.set('technician_id', technicianId)
    return get<{ slots: CalendarDay[]; service_type: { name: string; duration_minutes: number } }>(
      `/dealerships/${dealershipId}/availability?${params}`,
    )
  },

  // STEP 1 — book
  createAppointment: (body: {
    dealership_id: string
    customer_id: string
    vehicle_id: string
    service_type_id: string
    desired_start: string
    technician_id?: string
  }) => post<{ appointment: Appointment }>('/appointments', body),

  confirmAppointment: (id: string) =>
    patch<{ appointment: Appointment }>(`/appointments/${id}/confirm`, {}),

  cancelAppointment: (id: string) =>
    patch<{ appointment: Appointment }>(`/appointments/${id}/cancel`, {}),
}
