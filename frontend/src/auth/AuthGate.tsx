import { useEffect, useState, type ReactNode } from 'react'
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { api } from '../api'

type Phase = 'checking' | 'bootstrap' | 'login' | 'authed' | 'error'

export default function AuthGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>('checking')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [deviceLabel, setDeviceLabel] = useState('')
  const [bootstrapKey, setBootstrapKey] = useState('')
  const [enrollmentCode, setEnrollmentCode] = useState('')

  const checkStatus = () => {
    api
      .authStatus()
      .then((s) => setPhase(s.logged_in ? 'authed' : s.has_credentials ? 'login' : 'bootstrap'))
      .catch((e) => {
        setError(String(e))
        setPhase('error')
      })
  }

  useEffect(checkStatus, [])

  const doRegister = async (opts: { bootstrapKey?: string; enrollmentCode?: string }) => {
    setBusy(true)
    setError('')
    try {
      const label = deviceLabel.trim() || 'Unnamed device'
      const { options, challenge_token } = await api.registerBegin(label, opts)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const credential = await startRegistration({ optionsJSON: options as any })
      await api.registerComplete(credential, challenge_token, label)
      setPhase('authed')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const doLogin = async () => {
    setBusy(true)
    setError('')
    try {
      const { options, challenge_token } = await api.loginBegin()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const credential = await startAuthentication({ optionsJSON: options as any })
      await api.loginComplete(credential, challenge_token)
      setPhase('authed')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (phase === 'checking') {
    return <div className="p-8 text-center text-neutral-500">Loading...</div>
  }

  if (phase === 'authed') {
    return <>{children}</>
  }

  return (
    <div className="mx-auto max-w-sm px-4 py-16">
      <h1 className="text-xl font-semibold mb-1">MMR Passport Renewal Monitor</h1>
      <p className="text-sm text-neutral-500 mb-6">Admin access — Face ID / Touch ID only.</p>

      {phase === 'error' && <p className="text-sm text-red-600 mb-4">Couldn't reach the server: {error}</p>}

      {phase === 'login' && (
        <div className="space-y-4">
          <button
            onClick={doLogin}
            disabled={busy}
            className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy ? 'Waiting for Face ID / Touch ID…' : 'Log in with Passkey'}
          </button>

          <details className="text-xs text-neutral-500">
            <summary className="cursor-pointer select-none">Registering a new device?</summary>
            <div className="mt-3 space-y-2">
              <p>Generate a code from a device you're already logged in on (Status tab), then enter it here.</p>
              <input
                className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
                placeholder="Device label (e.g. iPhone)"
                value={deviceLabel}
                onChange={(e) => setDeviceLabel(e.target.value)}
              />
              <input
                className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1 font-mono"
                placeholder="Enrollment code"
                value={enrollmentCode}
                onChange={(e) => setEnrollmentCode(e.target.value)}
              />
              <button
                onClick={() => doRegister({ enrollmentCode })}
                disabled={busy || !enrollmentCode.trim()}
                className="w-full rounded bg-neutral-700 px-4 py-2 text-white text-sm disabled:opacity-50"
              >
                {busy ? 'Waiting for Face ID / Touch ID…' : 'Register this device'}
              </button>
            </div>
          </details>
        </div>
      )}

      {phase === 'bootstrap' && (
        <div className="space-y-3">
          <p className="text-xs text-neutral-500">
            No devices registered yet. Enter the one-time setup code to register this device as the first admin
            device.
          </p>
          <input
            className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
            placeholder="Device label (e.g. MacBook)"
            value={deviceLabel}
            onChange={(e) => setDeviceLabel(e.target.value)}
          />
          <input
            className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
            type="password"
            placeholder="One-time setup code"
            value={bootstrapKey}
            onChange={(e) => setBootstrapKey(e.target.value)}
          />
          <button
            onClick={() => doRegister({ bootstrapKey })}
            disabled={busy || !bootstrapKey.trim()}
            className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy ? 'Waiting for Face ID / Touch ID…' : 'Register this device'}
          </button>
        </div>
      )}

      {error && phase !== 'error' && <p className="mt-4 text-xs text-red-600 break-words">{error}</p>}
    </div>
  )
}
