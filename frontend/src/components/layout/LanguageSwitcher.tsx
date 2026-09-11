'use client'

import { useState } from 'react'
import { Globe } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { LANGUAGES, useLanguage } from '@/shared/i18n/LanguageProvider'

/**
 * Compact language picker shown in the app header. Kept lightweight so it doesn't
 * compete visually with the notification bell / user menu next to it: a globe icon
 * and the currently-selected flag. Full names in the dropdown come in BOTH the
 * English name and the native name so a user who reads only one still recognises
 * the option they want.
 */
export function LanguageSwitcher() {
  const { lang, setLang } = useLanguage()
  const [open, setOpen] = useState(false)
  const current = LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0]

  return (
    // The switcher itself must always be readable — the native names inside must
    // never get run through the translator.
    <div data-i18n-skip="true" className="inline-flex">
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        className="inline-flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:border-border hover:bg-surface-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Change language"
        title={`Language: ${current.label}`}
      >
        <Globe className="h-4 w-4" />
        <span className="text-base leading-none">{current.flag}</span>
        <span className="hidden md:inline text-xs">{current.native}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {LANGUAGES.map((l) => (
          <DropdownMenuItem
            key={l.code}
            onSelect={() => setLang(l.code)}
            className={l.code === lang ? 'bg-primary/5 font-medium' : ''}
          >
            <span className="text-base mr-2">{l.flag}</span>
            <span className="flex-1">{l.native}</span>
            <span className="text-xs text-muted-foreground ml-2">{l.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
    </div>
  )
}
