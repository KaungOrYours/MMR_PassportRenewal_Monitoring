const API_BASE = import.meta.env.VITE_API_BASE as string
const API_KEY = import.meta.env.VITE_API_KEY as string

export interface Watchlist {
  id: number
  full_name: string
  passport_no: string | null
  note: string | null
  active: boolean
  created_at: string
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
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
  createWatchlist: (data: { full_name: string; passport_no?: string; note?: string }) =>
    request<Watchlist>('/api/watchlist', { method: 'POST', body: JSON.stringify(data) }),
  updateWatchlist: (id: number, data: Partial<Pick<Watchlist, 'full_name' | 'passport_no' | 'note' | 'active'>>) =>
    request<Watchlist>(`/api/watchlist/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteWatchlist: (id: number) => request<void>(`/api/watchlist/${id}`, { method: 'DELETE' }),
  listMatches: () => request<MatchRecord[]>('/api/matches'),
  dismissMatch: (id: number) => request<void>(`/api/matches/${id}`, { method: 'DELETE' }),
  listSnapshots: () => request<Snapshot[]>('/api/snapshots'),
  snapshotEntries: (id: number, q = '') =>
    request<Entry[]>(`/api/snapshots/${id}/entries${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  searchEntries: (q: string) => request<EntrySearchResult[]>(`/api/entries/search?q=${encodeURIComponent(q)}`),
  checkNow: () => request<{ status: string }>('/api/check-now', { method: 'POST' }),
}
