'use client'

/**
 * Rounded filter-chip row — the shared version of the pattern already hand-rolled in the
 * supervision assignment queue and documents category filter. One chip is active at a
 * time (radio-style), matching every existing use of this pattern on the site.
 */
import { cn } from '@/lib/utils'

export interface FilterChipOption<T extends string> {
  value: T
  label: string
}

export interface FilterChipsProps<T extends string> {
  label?: string
  options: FilterChipOption<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
}

export function FilterChips<T extends string>({
  label, options, value, onChange, className,
}: FilterChipsProps<T>) {
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {label && <span className="text-label mr-1">{label}</span>}
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={cn(
            'px-2.5 py-1 rounded-full text-xs border transition',
            value === opt.value
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-transparent text-muted-foreground border-border hover:text-foreground',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
