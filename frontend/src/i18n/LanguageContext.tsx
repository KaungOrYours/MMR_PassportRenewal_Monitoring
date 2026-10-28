import { createContext, useContext, useState, type ReactNode } from 'react'
import { translations, type Language, type TranslationShape } from './translations'

const STORAGE_KEY = 'language'

function loadInitialLanguage(): Language {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'my' ? 'my' : 'en'
}

type LanguageContextValue = {
  language: Language
  setLanguage: (lang: Language) => void
  t: TranslationShape
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(loadInitialLanguage)

  const setLanguage = (lang: Language) => {
    localStorage.setItem(STORAGE_KEY, lang)
    setLanguageState(lang)
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t: translations[language] }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider')
  return ctx
}

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="inline-flex rounded-full border border-neutral-300 dark:border-neutral-700 p-0.5 text-xs font-medium">
      <button
        onClick={() => setLanguage('en')}
        aria-pressed={language === 'en'}
        className={`rounded-full px-2.5 py-1 transition-colors ${
          language === 'en'
            ? 'bg-blue-600 text-white'
            : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
        }`}
      >
        A
      </button>
      <button
        onClick={() => setLanguage('my')}
        aria-pressed={language === 'my'}
        className={`rounded-full px-2.5 py-1 transition-colors ${
          language === 'my'
            ? 'bg-blue-600 text-white'
            : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
        }`}
      >
        က
      </button>
    </div>
  )
}
