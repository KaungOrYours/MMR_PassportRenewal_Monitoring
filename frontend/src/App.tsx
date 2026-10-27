import { useEffect, useState } from 'react'
import { api } from './api'
import AuthGate from './auth/AuthGate'
import AlertsView from './views/AlertsView'
import ListsView from './views/ListsView'
import PublicAlertsView from './views/PublicAlertsView'
import PublicStatusView from './views/PublicStatusView'
import SignupView from './views/SignupView'
import StatusView from './views/StatusView'
import UserStatusView from './views/UserStatusView'
import WatchlistView from './views/WatchlistView'

const ADMIN_TABS = [
  { id: 'watchlist', label: 'Watchlist', component: WatchlistView },
  { id: 'alerts', label: 'Alerts', component: AlertsView },
  { id: 'lists', label: 'Lists', component: ListsView },
  { id: 'status', label: 'Status', component: StatusView },
] as const

type AdminTabId = (typeof ADMIN_TABS)[number]['id']

function AdminDashboard() {
  const [tab, setTab] = useState<AdminTabId>('watchlist')
  const Active = ADMIN_TABS.find((t) => t.id === tab)!.component

  return (
    <AuthGate>
      <div className="mx-auto max-w-4xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">MMR Passport Renewal Monitor — Admin</h1>
          <p className="text-sm text-neutral-500">Tracks the Myanmar Embassy Singapore approval list</p>
        </header>

        <nav className="mb-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
          {ADMIN_TABS.map((t) => (
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

const PUBLIC_TABS = [
  { id: 'signup', label: 'Sign Up', component: SignupView },
  { id: 'lists', label: 'Lists', component: ListsView },
  { id: 'alerts', label: 'Alerts', component: PublicAlertsView },
  { id: 'status', label: 'Status', component: PublicStatusView },
] as const

type PublicTabId = (typeof PUBLIC_TABS)[number]['id']

function PublicApp() {
  const [tab, setTab] = useState<PublicTabId>('signup')
  const [totalUsers, setTotalUsers] = useState<number | null>(null)
  const Active = PUBLIC_TABS.find((t) => t.id === tab)!.component

  useEffect(() => {
    api.publicStats().then((s) => setTotalUsers(s.total_users)).catch(() => {})
  }, [])

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">MMR Passport Renewal Monitor</h1>
        <p className="text-sm text-neutral-500">
          Get notified on Telegram the moment your name appears on the Myanmar Embassy Singapore's passport
          approval or renewal appointment lists.
        </p>
        {totalUsers !== null && (
          <p className="text-xs text-neutral-400 mt-1">{totalUsers} people are using this service</p>
        )}
      </header>

      <nav className="mb-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {PUBLIC_TABS.map((t) => (
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
  )
}

export default function App() {
  // no router library for a few-page app -- /admin is the Passkey-gated
  // dashboard, /status/<token> is a person's own read-only status, and
  // everything else is the public app (signup + read-only Lists/Alerts/Status)
  const path = window.location.pathname
  if (path.startsWith('/admin')) return <AdminDashboard />

  const statusMatch = path.match(/^\/status\/([^/]+)/)
  if (statusMatch) return <UserStatusView token={statusMatch[1]} />

  return <PublicApp />
}
