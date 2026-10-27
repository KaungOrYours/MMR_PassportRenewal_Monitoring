import { useEffect, useState } from 'react'
import { api, type Snapshot } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Website PDF (Lost & Seaman/Offshore)',
  telegram_renewal: 'Telegram channel (PV/PJ renewal)',
}

export default function PublicStatusView() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listSnapshots()
      .then(setSnapshots)
      .finally(() => setLoading(false))
  }, [])

  const latestBySource = Object.keys(SOURCE_LABELS).map((source) => ({
    source,
    label: SOURCE_LABELS[source],
    snapshot: snapshots.find((s) => s.source === source),
  }))

  if (loading) return <p>Loading...</p>

  return (
    <div className="space-y-4">
      {latestBySource.map(({ source, label, snapshot }) => (
        <div key={source} className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
          <h3 className="font-semibold">{label}</h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Last updated: {snapshot ? new Date(snapshot.fetched_at).toLocaleString() : 'not checked yet'}
          </p>
        </div>
      ))}
      <p className="text-xs text-neutral-500">Both lists are checked automatically every 3 hours.</p>
    </div>
  )
}
