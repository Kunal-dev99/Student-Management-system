'use client'

import { Badge } from '@/components/ui/badge'
import type { Relationship } from './api'

// Map person identities to the design-system semantic pill variants.
const VARIANT: Record<Relationship['relationshipType'], 'default' | 'success' | 'info' | 'secondary' | 'warning'> = {
  applicant: 'info',
  student: 'success',
  employee: 'warning',
  alumni: 'secondary',
  researcher: 'default',
}

export function RelationshipBadge({ type, current }: { type: Relationship['relationshipType']; current?: boolean }) {
  return (
    <Badge variant={VARIANT[type]}>
      {type}
      {current ? ' · current' : ''}
    </Badge>
  )
}
