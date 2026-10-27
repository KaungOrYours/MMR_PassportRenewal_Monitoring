import { useEffect, useState } from 'react'
import { api, type Snapshot } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Website PDF (Lost & Seaman/Offshore)',
  telegram_renewal: 'Telegram channel (PV/PJ renewal)',
}

function describeSnapshot(s: Snapshot): string {
  if (s.mode === 'bootstrap') return 'Watching for new posts from here forward (no history scanned).'
  return `${s.row_count} entries across ${s.page_count} page(s), extracted via ${s.mode}`
}

export default function StatusView() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [apiStatus, setApiStatus] = useState<'checking' | 'ok' | 'down'>('checking')
  const [dispatching, setDispatching] = useState(false)
  const [dispatchMsg, setDispatchMsg] = useState('')

  const load = () => {
    api
      .health()
      .then(() => setApiStatus('ok'))
      .catch(() => setApiStatus('down'))
    api.listSnapshots().then(setSnapshots).catch(() => {})
  }

  useEffect(load, [])

  const latestBySource = Object.keys(SOURCE_LABELS).map((source) => ({
    source,
    label: SOURCE_LABELS[source],
    snapshot: snapshots.find((s) => s.source === source),
  }))

  const triggerCheck = async () => {
    setDispatching(true)
    setDispatchMsg('')
    try {
      await api.checkNow()
      setDispatchMsg('Check dispatched — it will run on GitHub Actions in the next minute or two.')
    } catch (e) {
      setDispatchMsg(`Failed to dispatch: ${String(e)}`)
    } finally {
      setDispatching(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
        <div className="flex items-center gap-2">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              apiStatus === 'ok' ? 'bg-green-500' : apiStatus === 'down' ? 'bg-red-500' : 'bg-neutral-400'
            }`}
          />
          <span className="font-medium">
            API {apiStatus === 'ok' ? 'online' : apiStatus === 'down' ? 'unreachable' : 'checking...'}
          </span>
        </div>
      </div>

      {latestBySource.map(({ source, label, snapshot }) => (
        <div key={source} className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4 space-y-1">
          <h3 className="font-semibold">{label}</h3>
          {snapshot ? (
            <>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                {new Date(snapshot.fetched_at).toLocaleString()}
              </p>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">{describeSnapshot(snapshot)}</p>
            </>
          ) : (
            <p className="text-sm text-neutral-500">No checks recorded yet.</p>
          )}
        </div>
      ))}

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4 space-y-2">
        <h3 className="font-semibold">Schedule</h3>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Both checks run automatically every 3 hours via GitHub Actions. The embassy typically publishes on
          Sundays.
        </p>
        <button
          onClick={triggerCheck}
          disabled={dispatching}
          className="rounded bg-blue-600 px-4 py-2 text-white text-sm disabled:opacity-50"
        >
          {dispatching ? 'Dispatching...' : 'Check now'}
        </button>
        {dispatchMsg && <p className="text-sm text-neutral-500">{dispatchMsg}</p>}
      </div>
    </div>
  )
}
