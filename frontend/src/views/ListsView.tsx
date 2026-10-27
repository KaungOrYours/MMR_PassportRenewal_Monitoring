import { useEffect, useState } from 'react'
import { api, type Entry, type EntrySearchResult, type Snapshot } from '../api'

const SOURCE_LABELS: Record<string, string> = {
  embassy_pdf: 'Lost & Seaman/Offshore (website)',
  telegram_renewal: 'Renewal appointment (Telegram)',
}

export default function ListsView() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [searchResults, setSearchResults] = useState<EntrySearchResult[] | null>(null)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listSnapshots().then((snaps) => {
      setSnapshots(snaps)
      if (snaps.length > 0) setSelected(snaps[0].id)
      setLoading(false)
    })
  }, [])

  // searching (2+ chars) looks across every snapshot ever recorded, not
  // just the one currently selected in the dropdown
  useEffect(() => {
    if (q.trim().length >= 2) {
      api.searchEntries(q.trim()).then(setSearchResults)
    } else {
      setSearchResults(null)
    }
  }, [q])

  useEffect(() => {
    if (selected == null || searchResults !== null) return
    api.snapshotEntries(selected).then(setEntries)
  }, [selected, searchResults])

  if (loading) return <p>Loading...</p>
  if (snapshots.length === 0) return <p className="text-neutral-500">No lists have been checked yet.</p>

  const showingSearch = searchResults !== null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <select
          className="rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2 disabled:opacity-50"
          value={selected ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
          disabled={showingSearch}
        >
          {snapshots.map((s) => (
            <option key={s.id} value={s.id}>
              {new Date(s.fetched_at).toLocaleString()} — {s.row_count} entries ({s.mode})
            </option>
          ))}
        </select>
        <input
          className="flex-1 min-w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Search name or passport no. across the entire history"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {showingSearch && (
        <p className="text-xs text-neutral-500">
          Searching all recorded entries. Clear the search box to browse one check at a time.
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead className="bg-neutral-100 dark:bg-neutral-900 text-left">
            <tr>
              {showingSearch && <th className="px-3 py-2">Source / date</th>}
              <th className="px-3 py-2">Page</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Remark</th>
            </tr>
          </thead>
          <tbody>
            {showingSearch
              ? searchResults.map((e) => (
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
                ))
              : entries.map((e) => (
                  <tr key={e.id} className="border-t border-neutral-200 dark:border-neutral-800">
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
      {(showingSearch ? searchResults.length : entries.length) === 0 && (
        <p className="text-neutral-500">No entries match.</p>
      )}
    </div>
  )
}
