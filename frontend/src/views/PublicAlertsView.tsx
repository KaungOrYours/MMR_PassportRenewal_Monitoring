import { useEffect, useState } from 'react'
import { api, type PublicMatch } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Lost & Seaman/Offshore (website)',
  telegram_renewal: 'Renewal appointment (Telegram)',
}

export default function PublicAlertsView() {
  const [matches, setMatches] = useState<PublicMatch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .publicMatches()
      .then(setMatches)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading...</p>
  if (error) return <p className="text-red-600 text-sm">{error}</p>

  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500">
        People this service has already notified — names are partially hidden to protect their privacy.
      </p>
      {matches.length === 0 ? (
        <p className="text-neutral-500">No matches yet.</p>
      ) : (
        matches.map((m, i) => (
          <div key={i} className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{m.watchlist_name_masked}</h3>
              <span className="text-xs text-neutral-400">{SOURCE_LABELS[m.source] || m.source}</span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-neutral-600 dark:text-neutral-400">
              <div>
                <dt className="inline text-neutral-400">List name: </dt>
                <dd className="inline">{m.entry_name_masked}</dd>
              </div>
              <div>
                <dt className="inline text-neutral-400">Date: </dt>
                <dd className="inline">{m.approved_date || 'n/a'}</dd>
              </div>
            </dl>
            <p className="mt-2 text-xs text-neutral-400">{new Date(m.created_at).toLocaleString()}</p>
          </div>
        ))
      )}
    </div>
  )
}
