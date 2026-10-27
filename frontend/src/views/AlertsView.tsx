import { useEffect, useState } from 'react'
import { api, type MatchRecord } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Lost & Seaman/Offshore (website)',
  telegram_renewal: 'Renewal appointment (Telegram)',
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const isHigh = confidence === 'high'
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${
        isHigh
          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
          : 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200'
      }`}
    >
      {isHigh ? 'High confidence' : 'Medium confidence'}
    </span>
  )
}

export default function AlertsView() {
  const [matches, setMatches] = useState<MatchRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dismissing, setDismissing] = useState<number | null>(null)

  useEffect(() => {
    api
      .listMatches()
      .then(setMatches)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const dismiss = async (id: number) => {
    setDismissing(id)
    try {
      await api.dismissMatch(id)
      setMatches((prev) => prev.filter((m) => m.id !== id))
    } catch (e) {
      setError(String(e))
    } finally {
      setDismissing(null)
    }
  }

  if (loading) return <p>Loading...</p>
  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (matches.length === 0) return <p className="text-neutral-500">No matches yet.</p>

  return (
    <div className="space-y-3">
      {matches.map((m) => (
        <div key={m.id} className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">{m.watchlist_name}</h3>
              <p className="text-xs text-neutral-400">{SOURCE_LABELS[m.source] || m.source}</p>
            </div>
            <div className="flex items-center gap-2">
              <ConfidenceBadge confidence={m.confidence} />
              <button
                onClick={() => dismiss(m.id)}
                disabled={dismissing === m.id}
                className="text-xs text-red-600 hover:underline disabled:opacity-50"
                title="Dismiss this as a false positive"
              >
                Dismiss
              </button>
            </div>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-neutral-600 dark:text-neutral-400">
            <div>
              <dt className="inline text-neutral-400">List name: </dt>
              <dd className="inline">{m.entry.name}</dd>
            </div>
            <div>
              <dt className="inline text-neutral-400">ID: </dt>
              <dd className="inline font-mono">{m.entry.passport_no}</dd>
            </div>
            <div>
              <dt className="inline text-neutral-400">Date: </dt>
              <dd className="inline">{m.entry.approved_date || 'n/a'}</dd>
            </div>
            <div>
              <dt className="inline text-neutral-400">Matched on: </dt>
              <dd className="inline">{m.matched_on}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-neutral-400">{new Date(m.created_at).toLocaleString()}</p>
        </div>
      ))}
    </div>
  )
}
