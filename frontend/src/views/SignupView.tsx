import { useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../i18n/LanguageContext'

const emptyForm = { full_name: '', passport_no: '', telegram_chat_id: '', note: '' }

export default function SignupView() {
  const { t } = useLanguage()
  const [form, setForm] = useState(emptyForm)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [statusLink, setStatusLink] = useState('')
  const [telegramSent, setTelegramSent] = useState<boolean | null>(null)
  const [telegramError, setTelegramError] = useState('')

  const telegramIdTrimmed = form.telegram_chat_id.trim()
  const telegramConnected = telegramIdTrimmed.length > 0
  const telegramIdValid = !telegramConnected || /^\d{5,15}$/.test(telegramIdTrimmed)
  const canSubmit = form.full_name.trim().length > 0 && telegramConnected && telegramIdValid && termsAccepted

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
          <p className="font-medium text-green-800 dark:text-green-200">{t.done.onList}</p>
          <p className="text-sm text-green-700 dark:text-green-300">{t.done.explain}</p>
          {telegramSent === true && (
            <p className="text-xs text-green-700 dark:text-green-300">{t.done.sentOk}</p>
          )}
          {telegramSent === false && (
            <div className="rounded bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 p-2 text-xs text-amber-800 dark:text-amber-200">
              {t.done.sentFailPrefix}
              {telegramError ? `: ${telegramError}` : ''}. {t.done.sentFailHelp}
            </div>
          )}
          {statusLink && (
            <div className="rounded bg-white dark:bg-neutral-900 border border-green-200 dark:border-green-800 p-2">
              <p className="text-xs text-neutral-500 mb-1">{t.done.bookmarkNote}</p>
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
            {t.done.addAnother}
          </button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3 rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
          <div>
            <label className="block text-xs text-neutral-500 mb-1">{t.form.fullName}</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              placeholder={t.form.fullNamePlaceholder}
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">{t.form.passportNumber}</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              placeholder={t.form.passportPlaceholder}
              value={form.passport_no}
              onChange={(e) => setForm({ ...form, passport_no: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">
              {t.form.telegramIdLabel} <span className="text-red-500">* {t.form.telegramRequired}</span>
            </label>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
                placeholder={t.form.telegramIdPlaceholder}
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
                {t.form.connectTelegram}
              </a>
            </div>
            {telegramConnected && !telegramIdValid && (
              <p className="mt-1 text-xs text-red-600">{t.form.telegramInvalidFormat}</p>
            )}
            <p className="mt-1 text-xs text-neutral-500">
              {t.form.telegramHelpPrefix} <strong>{t.form.telegramHelpStart}</strong> {t.form.telegramHelpSuffix}
              <strong> {t.form.telegramHelpBold}</strong> {t.form.telegramHelpTail}
            </p>
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">{t.form.note}</label>
            <input
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </div>

          <div className="border-t border-neutral-200 dark:border-neutral-800 pt-3 space-y-2">
            <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">{t.terms.heading}</p>
            <div className="max-h-40 overflow-y-auto rounded border border-neutral-200 dark:border-neutral-800 p-2 text-xs text-neutral-500 space-y-2">
              <p>
                {t.terms.p1} <strong>{t.terms.p1Bold}</strong> {t.terms.p1Tail}
              </p>
              <p>
                <strong>{t.terms.p2Bold}</strong> {t.terms.p2}{' '}
                <strong>{t.terms.p2Bold2}</strong> {t.terms.p2Tail}
              </p>
              <p>
                <strong>{t.terms.p3Bold}</strong> {t.terms.p3}
              </p>
              <p>
                <strong>{t.terms.p4Bold}</strong> {t.terms.p4}
              </p>
              <p>{t.terms.p5}</p>
            </div>
            <label className="flex items-start gap-2 text-xs text-neutral-600 dark:text-neutral-400">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
              />
              <span>{t.terms.checkbox}</span>
            </label>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            disabled={submitting || !canSubmit}
            className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {submitting ? t.form.submitting : t.form.submit}
          </button>
          {!canSubmit && (
            <p className="text-xs text-neutral-500 text-center">
              {!telegramConnected
                ? t.form.hintNoTelegram
                : !telegramIdValid
                ? t.form.telegramInvalidFormat
                : !termsAccepted
                ? t.form.hintNoTerms
                : t.form.hintNoName}
            </p>
          )}
        </form>
      )}
    </div>
  )
}
