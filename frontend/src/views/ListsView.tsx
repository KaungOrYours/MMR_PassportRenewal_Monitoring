import { useState, type FormEvent } from 'react'
import { api, ApiError, type EntrySearchResult } from '../api'
import { useLanguage } from '../i18n/LanguageContext'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Lost & Seaman/Offshore (website)',
  telegram_renewal: 'Renewal appointment (Telegram)',
}

const MIN_CHARS = 3

// Public Lists tab: search only. There is deliberately no way to page through the
// lists, and a search runs on submit rather than per keystroke because each one
// counts against the visitor's hourly allowance.
export default function ListsView() {
  const { t } = useLanguage()
  const [q, setQ] = useState('')
  const [results, setResults] = useState<EntrySearchResult[] | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const term = q.trim()
    setResults(null)
    if (term.replace(/\s+/g, '').length < MIN_CHARS) {
      setMessage(t.lists.invalid)
      return
    }
    setMessage(null)
    setBusy(true)
    try {
      const res = await api.searchEntries(term)
      if (res.too_many) setMessage(t.lists.tooMany)
      else setResults(res.results)
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setMessage(t.lists.rateLimited)
      else if (err instanceof ApiError && err.status === 400) setMessage(t.lists.invalid)
      else setMessage(t.lists.error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex flex-wrap gap-2 items-center">
        <input
          className="flex-1 min-w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder={t.lists.searchPlaceholder}
          value={q}
          maxLength={100}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? t.lists.searching : t.lists.searchButton}
        </button>
      </form>
      <p className="text-xs text-neutral-500">{t.lists.hint}</p>
      {message && <p className="text-sm text-amber-700 dark:text-amber-400">{message}</p>}

      {results !== null && results.length === 0 && <p className="text-neutral-500">{t.lists.noMatches}</p>}
      {results !== null && results.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-sm">
              <thead className="bg-neutral-100 dark:bg-neutral-900 text-left">
                <tr>
                  <th className="px-3 py-2">Source / date</th>
                  <th className="px-3 py-2">Page</th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Remark</th>
                </tr>
              </thead>
              <tbody>
                {results.map((e) => (
                  <tr key={e.id} className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2 text-xs text-neutral-500">
                      {SOURCE_LABELS[e.source] || e.source}
                      <br />
                      {new Date(e.fetched_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2">{e.page_no}</td>
                    <td className="px-3 py-2 font-medium">{e.name}</td>
                    <td className="px-3 py-2 font-mono">{e.passport_no}</td>
                    <td className="px-3 py-2">{e.approved_date || '—'}</td>
                    <td className="px-3 py-2 text-neutral-500">{e.remark || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
