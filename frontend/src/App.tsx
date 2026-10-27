import { useState } from 'react'
import AuthGate from './auth/AuthGate'
import AlertsView from './views/AlertsView'
import ListsView from './views/ListsView'
import SignupView from './views/SignupView'
import StatusView from './views/StatusView'
import WatchlistView from './views/WatchlistView'

const TABS = [
  { id: 'watchlist', label: 'Watchlist', component: WatchlistView },
  { id: 'alerts', label: 'Alerts', component: AlertsView },
  { id: 'lists', label: 'Lists', component: ListsView },
  { id: 'status', label: 'Status', component: StatusView },
] as const

type TabId = (typeof TABS)[number]['id']

function AdminDashboard() {
  const [tab, setTab] = useState<TabId>('watchlist')
  const Active = TABS.find((t) => t.id === tab)!.component

  return (
    <AuthGate>
      <div className="mx-auto max-w-4xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">MMR Passport Renewal Monitor — Admin</h1>
          <p className="text-sm text-neutral-500">Tracks the Myanmar Embassy Singapore approval list</p>
        </header>

        <nav className="mb-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <main>
          <Active />
        </main>
      </div>
    </AuthGate>
  )
}

export default function App() {
  // no router library for a two-page app -- /admin is the Passkey-gated
  // dashboard, everything else is the public self-service signup
  const isAdmin = window.location.pathname.startsWith('/admin')
  return isAdmin ? <AdminDashboard /> : <SignupView />
}
