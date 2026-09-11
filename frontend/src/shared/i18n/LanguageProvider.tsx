'use client'

/**
 * Language state — persisted in localStorage, exposed through a lightweight context.
 *
 * Deliberately narrow: only the primary navigation is translated today. Settings, forms,
 * dialogs and error copy stay in English so that a user who picks a language they don't
 * read can still find the switcher and change back.
 */

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { LANGUAGES, TRANSLATIONS, translate, translateSubtree, type LanguageCode } from './translations'

const STORAGE_KEY = 'pgr.ui.language'

interface LanguageState {
  lang: LanguageCode
  setLang: (l: LanguageCode) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageState | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<LanguageCode>('en')

  // Read the saved value once on mount. sessionStorage/localStorage can throw in
  // private-browsing modes — swallow those and stay on English.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as LanguageCode | null
      if (saved && saved in TRANSLATIONS) setLangState(saved)
    } catch { /* ignore */ }
  }, [])

  // Reflect the choice on <html lang="…"> for screen readers, run the initial
  // translation pass, and observe subsequent DOM mutations so newly rendered
  // pages get translated automatically without wrapping every string with t().
  const langRef = useRef(lang)
  langRef.current = lang
  useEffect(() => {
    try {
      document.documentElement.lang = lang
    } catch { /* ignore SSR */ }
    try {
      translateSubtree(document.body, lang)
    } catch { /* SSR or hydration edge */ }
  }, [lang])

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    // Debounced batch — React can produce many mutations per render; walking the
    // subtree once per animation frame keeps the observer cheap.
    let pending = false
    const observer = new MutationObserver(() => {
      if (pending) return
      pending = true
      requestAnimationFrame(() => {
        pending = false
        try { translateSubtree(document.body, langRef.current) } catch { /* ignore */ }
      })
    })
    observer.observe(document.body, {
      childList: true, subtree: true, characterData: true,
    })
    return () => observer.disconnect()
  }, [])

  const setLang = (l: LanguageCode) => {
    setLangState(l)
    try { localStorage.setItem(STORAGE_KEY, l) } catch { /* ignore */ }
    // Instant sweep — walk the DOM before the next paint so the user never sees
    // a frame in the old language while React schedules its re-render.
    try {
      document.documentElement.lang = l
      translateSubtree(document.body, l)
    } catch { /* ignore SSR */ }
  }

  const t = (key: string) => translate(lang, key)

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage(): LanguageState {
  const ctx = useContext(LanguageContext)
  if (!ctx) {
    // Fallback for anything mounted outside the provider (SSR, dev). English only.
    return { lang: 'en', setLang: () => undefined, t: (k) => k }
  }
  return ctx
}

export { LANGUAGES }
export type { LanguageCode }
