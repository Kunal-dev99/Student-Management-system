'use client'

/**
 * Persona tags — the capacities a Person holds towards the institution (applicant, student,
 * employee, alumni, researcher, clinical trainee). One Person can hold several at once, so
 * these render as a row of small badges. A currently-valid relationship (no end date) is
 * solid; an ended one is muted/outlined, so "was a student, now alumni" reads at a glance.
 */
import { Badge } from '@/components/ui/badge'
import type { Relationship, RelationshipType } from '@/features/persons/api'

const LABELS: Record<RelationshipType, string> = {
  applicant: 'Applicant',
  student: 'Student',
  employee: 'Staff',
  alumni: 'Alumni',
  researcher: 'Researcher',
  clinical_trainee: 'Clinical trainee',
}

// Distinct types, current ones first, each with whether any current relationship of that type exists.
function summarise(relationships: Relationship[]): { type: RelationshipType; current: boolean }[] {
  const byType = new Map<RelationshipType, boolean>()
  for (const r of relationships) {
    const isCurrent = r.validTo == null
    byType.set(r.relationshipType, (byType.get(r.relationshipType) ?? false) || isCurrent)
  }
  return [...byType.entries()]
    .map(([type, current]) => ({ type, current }))
    .sort((a, b) => Number(b.current) - Number(a.current))
}

export function PersonaTags({
  relationships,
  className = '',
  emptyLabel,
}: {
  relationships: Relationship[] | undefined
  className?: string
  /** When set, shows this muted text instead of rendering nothing when there are no personas. */
  emptyLabel?: string
}) {
  const items = summarise(relationships ?? [])
  if (items.length === 0) {
    return emptyLabel ? <span className={`text-xs text-muted-foreground ${className}`}>{emptyLabel}</span> : null
  }
  return (
    <span className={`inline-flex flex-wrap gap-1 ${className}`}>
      {items.map(({ type, current }) => (
        <Badge
          key={type}
          variant={current ? 'secondary' : 'outline'}
          className={current ? '' : 'text-muted-foreground line-through decoration-muted-foreground/40'}
          title={current ? `Current ${LABELS[type].toLowerCase()}` : `Former ${LABELS[type].toLowerCase()}`}
        >
          {LABELS[type] ?? type}
        </Badge>
      ))}
    </span>
  )
}
