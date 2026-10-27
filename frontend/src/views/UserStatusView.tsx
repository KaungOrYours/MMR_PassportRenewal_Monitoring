import { useEffect, useState } from 'react'
import { api, type PublicStatus } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Lost & Seaman/Offshore (website)',
  telegram_renewal: 'Renewal appointment (Telegram)',
}

export default function UserStatusView({ token }: { token: string }) {
  const [status, setStatus] = useState<PublicStatus | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .statusByToken(token)
      .then(setStatus)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [token])

  return (
    <div className="mx-auto max-w-sm px-4 py-16">
      <h1 className="text-xl font-semibold mb-1">MMR Passport Renewal Monitor</h1>
      <p className="text-sm text-neutral-500 mb-6">Your status</p>

      {loading && <p className="text-neutral-500">Loading…</p>}

      {error && (
        <p className="text-sm text-red-600">
          Couldn't find this link. If you just signed up, double-check you copied the full URL.
        </p>
      )}

      {status && (
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4 space-y-3">
          <div>
            <p className="font-medium">{status.full_name}</p>
            <p className="text-sm text-neutral-500 font-mono">{status.passport_no || 'No passport number on file'}</p>
          </div>

          {status.status === 'paused' && (
            <div className="rounded bg-neutral-100 dark:bg-neutral-800 px-3 py-2 text-sm text-neutral-600 dark:text-neutral-400">
              Monitoring is currently paused for you. Contact the admin if this is unexpected.
            </div>
          )}

          {status.status === 'pending' && (
            <div className="rounded bg-amber-100 dark:bg-amber-900 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
              Pending — we're still watching. You'll get a Telegram message the moment your name appears.
            </div>
          )}

          {status.status === 'matched' && (
            <div className="rounded bg-green-100 dark:bg-green-900 px-3 py-2 text-sm text-green-800 dark:text-green-200 space-y-1">
              <p className="font-medium">Found on a list!</p>
              {status.appointment_date && <p>Date: {status.appointment_date}</p>}
              {status.matched_source && <p>{SOURCE_LABELS[status.matched_source] || status.matched_source}</p>}
              <p className="text-xs">Always verify independently before relying on this for travel/appointment plans.</p>
            </div>
          )}

          <p className="text-xs text-neutral-400 pt-2 border-t border-neutral-200 dark:border-neutral-800">
            Bookmark this page to check back anytime — this link is unique to you.
          </p>
        </div>
      )}
    </div>
  )
}
