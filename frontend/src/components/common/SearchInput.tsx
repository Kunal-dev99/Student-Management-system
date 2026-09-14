'use client'

/**
 * Debounced search box — the shared version of the pattern already hand-rolled in
 * Persons/Recruitment/etc. `onChange` fires `delayMs` after typing stops, not on every
 * keystroke, so it's safe to wire straight into a query key without spamming the API.
 */
import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  delayMs?: number
  className?: string
}

export function SearchInput({
  value, onChange, placeholder = 'Search…', delayMs = 300, className,
}: SearchInputProps) {
  const [draft, setDraft] = useState(value)

  // Keep the box in sync if the caller resets `value` externally (e.g. a "Clear filters").
  useEffect(() => setDraft(value), [value])

  useEffect(() => {
    if (draft === value) return
    const t = setTimeout(() => onChange(draft), delayMs)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, delayMs])

  return (
    <div className={cn('relative max-w-sm', className)}>
      <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input
        placeholder={placeholder}
        className="pl-8"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
    </div>
  )
}
