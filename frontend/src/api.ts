import { getSessionToken } from './auth/session'

const API_BASE = import.meta.env.VITE_API_BASE as string

export interface Watchlist {
  id: number
  full_name: string
  passport_no: string | null
  telegram_chat_id: string | null
  note: string | null
  active: boolean
  lookup_token: string | null
  created_at: string
  // only set on the response from createWatchlist
  telegram_sent: boolean | null
  telegram_error: string | null
}

export interface PublicStatus {
  full_name: string
  passport_no: string | null
  active: boolean
  status: 'pending' | 'matched' | 'paused'
  appointment_date: string | null
  matched_name_on_list: string | null
  matched_source: string | null
}

export interface Entry {
  id: number
  page_no: number
  name: string
  passport_no: string
  id_kind: string
  approved_date: string | null
  remark: string | null
}

export interface EntrySearchResult extends Entry {
  snapshot_id: number
  source: string
  fetched_at: string
}

export interface Snapshot {
  id: number
  fetched_at: string
  source: string
  page_count: number
  mode: string
  row_count: number
}

export interface MatchRecord {
  id: number
  watchlist_id: number
  source: string
  watchlist_name: string
  entry: Entry
  snapshot_id: number
  confidence: string
  matched_on: string
  score: number
  created_at: string
}

export interface AuthStatus {
  has_credentials: boolean
  logged_in: boolean
}

export interface Device {
  id: number
  device_label: string | null
  created_at: string
}

export interface PublicMatch {
  watchlist_name_masked: string
  entry_name_masked: string
  passport_no: string | null
  approved_date: string | null
  source: string
  created_at: string
}

export interface PublicStats {
  total_users: number
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getSessionToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  listWatchlist: () => request<Watchlist[]>('/api/watchlist'),
  createWatchlist: (data: {
    full_name: string
    passport_no?: string
    telegram_chat_id?: string
    note?: string
    terms_accepted: boolean
  }) => request<Watchlist>('/api/watchlist', { method: 'POST', body: JSON.stringify(data) }),
  updateWatchlist: (
    id: number,
    data: Partial<Pick<Watchlist, 'full_name' | 'passport_no' | 'telegram_chat_id' | 'note' | 'active'>>,
  ) => request<Watchlist>(`/api/watchlist/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteWatchlist: (id: number) => request<void>(`/api/watchlist/${id}`, { method: 'DELETE' }),
  statusByToken: (token: string) => request<PublicStatus>(`/api/watchlist/status/${token}`),
  listMatches: () => request<MatchRecord[]>('/api/matches'),
  dismissMatch: (id: number) => request<void>(`/api/matches/${id}`, { method: 'DELETE' }),
  publicMatches: () => request<PublicMatch[]>('/api/public/matches'),
  publicStats: () => request<PublicStats>('/api/public/stats'),
  listSnapshots: () => request<Snapshot[]>('/api/snapshots'),
  snapshotEntries: (id: number, q = '') =>
    request<Entry[]>(`/api/snapshots/${id}/entries${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  searchEntries: (q: string) => request<EntrySearchResult[]>(`/api/entries/search?q=${encodeURIComponent(q)}`),
  checkNow: () => request<{ status: string }>('/api/check-now', { method: 'POST' }),

  authStatus: () => request<AuthStatus>('/api/auth/status'),
  registerBegin: (deviceLabel: string, opts: { bootstrapKey?: string; enrollmentCode?: string } = {}) =>
    request<{ options: unknown; challenge_token: string }>('/api/auth/register/begin', {
      method: 'POST',
      headers: opts.bootstrapKey ? { 'X-API-Key': opts.bootstrapKey } : {},
      body: JSON.stringify({ device_label: deviceLabel, enrollment_code: opts.enrollmentCode }),
    }),
  registerComplete: (credential: unknown, challengeToken: string, deviceLabel: string) =>
    request<{ status: string; session_token: string }>('/api/auth/register/complete', {
      method: 'POST',
      body: JSON.stringify({ credential, challenge_token: challengeToken, device_label: deviceLabel }),
    }),
  loginBegin: () => request<{ options: unknown; challenge_token: string }>('/api/auth/login/begin', { method: 'POST' }),
  loginComplete: (credential: unknown, challengeToken: string) =>
    request<{ status: string; session_token: string }>('/api/auth/login/complete', {
      method: 'POST',
      body: JSON.stringify({ credential, challenge_token: challengeToken }),
    }),
  logout: () => request<{ status: string }>('/api/auth/logout', { method: 'POST' }),
  logoutAll: () => request<{ status: string }>('/api/auth/logout-all', { method: 'POST' }),
  createEnrollmentCode: () =>
    request<{ code: string; expires_in_seconds: number }>('/api/auth/enrollment-code', { method: 'POST' }),
  listDevices: () => request<Device[]>('/api/auth/devices'),
  revokeDevice: (id: number) => request<void>(`/api/auth/devices/${id}`, { method: 'DELETE' }),
}
