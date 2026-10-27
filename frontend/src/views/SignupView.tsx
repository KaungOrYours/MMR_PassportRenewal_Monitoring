import { useState } from 'react'
import { api } from '../api'

const emptyForm = { full_name: '', passport_no: '', telegram_chat_id: '', note: '' }

export default function SignupView() {
  const [form, setForm] = useState(emptyForm)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [statusLink, setStatusLink] = useState('')
  const [telegramSent, setTelegramSent] = useState<boolean | null>(null)
  const [telegramError, setTelegramError] = useState('')

  const telegramConnected = form.telegram_chat_id.trim().length > 0
  const canSubmit = form.full_name.trim().length > 0 && telegramConnected && termsAccepted

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      const created = await api.createWatchlist({
        full_name: form.full_name.trim().toUpperCase(),
        passport_no: form.passport_no.trim().toUpperCase() || undefined,
        telegram_chat_id: form.telegram_chat_id.trim(),
        note: form.note.trim() || undefined,
        terms_accepted: true,
      })
      if (created.lookup_token) {
        setStatusLink(`${window.location.origin}/status/${created.lookup_token}`)
      }
      setTelegramSent(created.telegram_sent)
      setTelegramError(created.telegram_error || '')
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
          {telegramSent === true && (
            <p className="text-xs text-green-700 dark:text-green-300">
              ✅ A confirmation message was sent to your Telegram — check your chat with the bot.
            </p>
          )}
          {telegramSent === false && (
            <div className="rounded bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 p-2 text-xs text-amber-800 dark:text-amber-200">
              ⚠️ We couldn't send you a Telegram message{telegramError ? `: ${telegramError}` : ''}.<br />
              Make sure you've messaged <strong>@MMR_PassportRenewalMonitoringBot</strong> on Telegram first (send
              it <code>/start</code>), and that your Telegram ID is correct — get it from{' '}
              <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer" className="underline">
                @userinfobot
              </a>
              . You're still on the list either way; you can check your status with the link below.
            </div>
          )}
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
              setTermsAccepted(false)
              setDone(false)
              setStatusLink('')
              setTelegramSent(null)
              setTelegramError('')
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
            <label className="block text-xs text-neutral-500 mb-1">
              Your Telegram ID <span className="text-red-500">* required</span>
            </label>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
                placeholder="e.g. 123456789"
                value={form.telegram_chat_id}
                onChange={(e) => setForm({ ...form, telegram_chat_id: e.target.value })}
                required
              />
              <a
                href="https://t.me/MMR_PassportRenewalMonitoringBot?start=1"
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded bg-sky-500 px-3 py-2 text-white text-sm hover:bg-sky-600"
              >
                Connect Telegram
              </a>
            </div>
            <p className="mt-1 text-xs text-neutral-500">
              Tap "Connect Telegram", then tap <strong>Start</strong> in the chat that opens — our bot replies
              instantly with your ID (tap it to copy), paste it above. We'll only message you there, nowhere else.
              <strong> We can't notify you without this</strong> — Telegram doesn't let a bot message someone who
              hasn't started a chat with it first.
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

          <div className="border-t border-neutral-200 dark:border-neutral-800 pt-3 space-y-2">
            <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Terms & Conditions</p>
            <div className="max-h-40 overflow-y-auto rounded border border-neutral-200 dark:border-neutral-800 p-2 text-xs text-neutral-500 space-y-2">
              <p>
                This is a free, volunteer-run, non-commercial community tool built to help Myanmar citizens in
                Singapore avoid manually checking the Embassy's approval lists every week. It is{' '}
                <strong>not affiliated with, endorsed by, or operated on behalf of</strong> the Embassy of the
                Republic of the Union of Myanmar in Singapore, or any Myanmar or Singapore government agency.
              </p>
              <p>
                <strong>Your data, your responsibility.</strong> By submitting, you confirm the information is
                your own, or that you have the consent of the person it belongs to. Your name, passport number,
                and Telegram ID are stored only to (a) match against the Embassy's publicly posted lists and (b)
                send you a Telegram alert when a match is found. This data is{' '}
                <strong>never sold, shared with third parties, or used for the developer's personal gain</strong> —
                it exists solely to operate this notification service for the Myanmar community.
              </p>
              <p>
                <strong>No guarantee of accuracy.</strong> Matching relies on OCR and automated text extraction
                from scanned documents, which can misread names or passport numbers, and the Embassy's source
                lists can change format without notice. This service may miss a match, misfire on a shared name,
                or experience downtime. It is provided "as is," with no warranty of any kind, and must not be
                relied on as your sole source of information — always verify independently with the Embassy
                before taking any action (e.g. travel plans) based on an alert.
              </p>
              <p>
                <strong>Limitation of liability.</strong> To the fullest extent permitted under the laws of the
                Republic of Singapore and the laws of the Republic of the Union of Myanmar, the developer of this
                tool shall not be liable for any loss, damage, missed appointment, or other consequence arising
                from reliance on, use of, or inability to use this service. You use this service entirely at your
                own risk.
              </p>
              <p>
                You may request removal of your data at any time by messaging the bot or contacting the
                developer. Continued use of this service is subject to these terms as they may be updated from
                time to time.
              </p>
            </div>
            <label className="flex items-start gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
              />
              <span>
                I have read and agree to the Terms & Conditions above, and I confirm this information is my own
                (or submitted with the owner's consent).
              </span>
            </label>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            disabled={submitting || !canSubmit}
            className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {submitting ? 'Adding…' : 'Notify me'}
          </button>
          {!canSubmit && (
            <p className="text-xs text-neutral-500 text-center">
              {!telegramConnected
                ? 'Connect Telegram and enter your ID above to continue.'
                : !termsAccepted
                ? 'Please accept the Terms & Conditions to continue.'
                : 'Enter your full name to continue.'}
            </p>
          )}
        </form>
      )}
    </div>
  )
}
