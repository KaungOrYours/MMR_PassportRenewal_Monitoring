import { useState } from 'react'
import { api } from '../api'

function toTitleCase(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ')
}

const emptyForm = { full_name: '', passport_no: '', telegram_chat_id: '', note: '' }

export default function SignupView() {
  const [form, setForm] = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [statusLink, setStatusLink] = useState('')

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.full_name.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const created = await api.createWatchlist({
        full_name: toTitleCase(form.full_name),
        passport_no: form.passport_no.trim().toUpperCase() || undefined,
        telegram_chat_id: form.telegram_chat_id.trim() || undefined,
        note: form.note.trim() || undefined,
      })
      if (created.lookup_token) {
        setStatusLink(`${window.location.origin}/status/${created.lookup_token}`)
      }
      setDone(true)
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      {done ? (
        <div className="rounded-lg border border-green-200 dark:border-green-900 bg-green-50 dark:bg-green-950 p-4 space-y-3">
          <p className="font-medium text-green-800 dark:text-green-200">You're on the list.</p>
          <p className="text-sm text-green-700 dark:text-green-300">
            We'll check the embassy's lists automatically and message you on Telegram if your name and passport
            number appear.
          </p>
          {statusLink && (
            <div className="rounded bg-white dark:bg-neutral-900 border border-green-200 dark:border-green-800 p-2">
              <p className="text-xs text-neutral-500 mb-1">Bookmark this link to check your status anytime:</p>
              <a href={statusLink} className="text-xs text-blue-600 hover:underline break-all">
                {statusLink}
              </a>
            </div>
          )}
          <button
            onClick={() => {
              setForm(emptyForm)
              setDone(false)
              setStatusLink('')
            }}
            className="text-sm text-blue-600 hover:underline"
          >
            Add another person
          </button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3 rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Full name</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              placeholder="As it appears on your passport"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Passport number</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              placeholder="e.g. MG123456"
              value={form.passport_no}
              onChange={(e) => setForm({ ...form, passport_no: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Your Telegram ID</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              placeholder="e.g. 123456789"
              value={form.telegram_chat_id}
              onChange={(e) => setForm({ ...form, telegram_chat_id: e.target.value })}
            />
            <p className="mt-1 text-xs text-neutral-500">
              Message{' '}
              <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                @userinfobot
              </a>{' '}
              on Telegram — it replies instantly with your ID. We'll message you there, nowhere else.
            </p>
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Note (optional)</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </div>

          <p className="text-xs text-neutral-500 border-t border-neutral-200 dark:border-neutral-800 pt-3">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">Your data, your responsibility:</span>{' '}
            this is a best-effort personal monitoring tool, not an official embassy service. Matching can miss
            entries (OCR errors, unclear names) or misfire (shared names) — always verify independently before
            relying on an alert. Only submit your own information, or someone else's with their consent.
          </p>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            disabled={submitting}
            className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {submitting ? 'Adding…' : 'Notify me'}
          </button>
        </form>
      )}
    </div>
  )
}
