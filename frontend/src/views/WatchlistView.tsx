import { useEffect, useState } from 'react'
import { api, type MatchRecord, type Watchlist } from '../api'

function toTitleCase(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ')
}

type RowStatus =
  | { kind: 'paused' }
  | { kind: 'pending' }
  | { kind: 'matched'; date: string | null }

function statusFor(w: Watchlist, matchesByWatchlist: Map<number, MatchRecord>): RowStatus {
  if (!w.active) return { kind: 'paused' }
  const match = matchesByWatchlist.get(w.id)
  if (match) return { kind: 'matched', date: match.entry.approved_date }
  return { kind: 'pending' }
}

function StatusBadge({ status, onClick }: { status: RowStatus; onClick: () => void }) {
  const styles: Record<RowStatus['kind'], string> = {
    paused: 'bg-neutral-200 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400',
    pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    matched: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  }
  const label =
    status.kind === 'paused'
      ? 'Paused'
      : status.kind === 'pending'
        ? 'Pending'
        : `Appointment: ${status.date || 'date n/a'}`

  return (
    <button onClick={onClick} className={`rounded px-2 py-0.5 text-xs ${styles[status.kind]}`}>
      {label}
    </button>
  )
}

const emptyForm = { full_name: '', passport_no: '', telegram_chat_id: '', note: '' }

export default function WatchlistView() {
  const [items, setItems] = useState<Watchlist[]>([])
  const [matches, setMatches] = useState<MatchRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([api.listWatchlist(), api.listMatches()])
      .then(([w, m]) => {
        setItems(w)
        setMatches(m)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.full_name.trim()) return
    setSubmitting(true)
    try {
      await api.createWatchlist({
        full_name: toTitleCase(form.full_name),
        passport_no: form.passport_no.trim().toUpperCase() || undefined,
        telegram_chat_id: form.telegram_chat_id.trim() || undefined,
        note: form.note.trim() || undefined,
      })
      setForm(emptyForm)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const toggleActive = async (w: Watchlist) => {
    await api.updateWatchlist(w.id, { active: !w.active })
    load()
  }

  // most recent match per person, preferring one that actually has a date
  const matchesByWatchlist = new Map<number, MatchRecord>()
  for (const m of matches) {
    const existing = matchesByWatchlist.get(m.watchlist_id)
    if (!existing || (!existing.entry.approved_date && m.entry.approved_date)) {
      matchesByWatchlist.set(m.watchlist_id, m)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="flex flex-wrap gap-2 rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
        <input
          className="flex-1 min-w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Full name"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
        />
        <input
          className="w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Passport no. (optional)"
          value={form.passport_no}
          onChange={(e) => setForm({ ...form, passport_no: e.target.value })}
        />
        <input
          className="w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Telegram ID (optional)"
          value={form.telegram_chat_id}
          onChange={(e) => setForm({ ...form, telegram_chat_id: e.target.value })}
        />
        <input
          className="w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Note (optional)"
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
        <button
          disabled={submitting}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Add
        </button>
      </form>

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4 space-y-2 text-xs text-neutral-500">
        <p>
          <span className="font-medium text-neutral-700 dark:text-neutral-300">Telegram ID (optional):</span> if set,
          alerts for this person go to their own Telegram instead of the default chat. To find your Telegram ID,
          message{' '}
          <a
            href="https://t.me/userinfobot"
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 hover:underline"
          >
            @userinfobot
          </a>{' '}
          on Telegram — it replies instantly with your ID.
        </p>
        <p>
          <span className="font-medium text-neutral-700 dark:text-neutral-300">Your data, your responsibility:</span>{' '}
          this is a best-effort personal monitoring tool, not an official embassy service. Matching can miss entries
          (OCR errors, unclear names) or misfire (shared names). Always verify independently before relying on an
          alert, and do not submit anyone's information without their consent.
        </p>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {loading ? (
        <p>Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-neutral-500">No one on the watchlist yet. Add a name above.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-sm">
            <thead className="bg-neutral-100 dark:bg-neutral-900 text-left">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Passport No.</th>
                <th className="px-3 py-2">Telegram ID</th>
                <th className="px-3 py-2">Note</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id} className="border-t border-neutral-200 dark:border-neutral-800">
                  <td className="px-3 py-2 font-medium">{w.full_name}</td>
                  <td className="px-3 py-2 font-mono">{w.passport_no || '—'}</td>
                  <td className="px-3 py-2 font-mono">{w.telegram_chat_id || '—'}</td>
                  <td className="px-3 py-2 text-neutral-500">{w.note || '—'}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={statusFor(w, matchesByWatchlist)} onClick={() => toggleActive(w)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
