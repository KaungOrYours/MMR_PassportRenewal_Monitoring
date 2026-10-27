import { useEffect, useState } from 'react'
import { api, type Entry, type Snapshot } from '../api'

export default function ListsView() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listSnapshots().then((snaps) => {
      setSnapshots(snaps)
      if (snaps.length > 0) setSelected(snaps[0].id)
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    if (selected == null) return
    api.snapshotEntries(selected, q).then(setEntries)
  }, [selected, q])

  if (loading) return <p>Loading...</p>
  if (snapshots.length === 0) return <p className="text-neutral-500">No lists have been checked yet.</p>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <select
          className="rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          value={selected ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {snapshots.map((s) => (
            <option key={s.id} value={s.id}>
              {new Date(s.fetched_at).toLocaleString()} — {s.row_count} entries ({s.mode})
            </option>
          ))}
        </select>
        <input
          className="flex-1 min-w-40 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
          placeholder="Search name or passport no."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead className="bg-neutral-100 dark:bg-neutral-900 text-left">
            <tr>
              <th className="px-3 py-2">Page</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Remark</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
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
      {entries.length === 0 && <p className="text-neutral-500">No entries match.</p>}
    </div>
  )
}
