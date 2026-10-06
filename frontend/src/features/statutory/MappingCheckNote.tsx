'use client'

/**
 * Live check of a mapping while it is being edited (custom attribute governance, Phase 4): the
 * backend says whether it would be refused (errors) and what deserves a second look (warnings —
 * a coded HESA field fed by a text attribute, an attribute requested for a different field, an
 * attribute under review, a path outside the catalogue). Reports validity up so Save can wait.
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, XCircle } from 'lucide-react'
import { useMappingCheck } from '@/features/statutory/api'

export function MappingCheckNote({
  profileId, targetField, sourceExpression, transform, mappingId, onValidity,
}: {
  profileId: string
  targetField: string
  sourceExpression: string
  transform?: string
  mappingId?: string
  onValidity: (valid: boolean) => void
}) {
  // Debounce: check once typing pauses, not on every keystroke.
  const [probe, setProbe] = useState({ targetField, sourceExpression, transform })
  useEffect(() => {
    const t = setTimeout(() => setProbe({ targetField: targetField.trim(), sourceExpression: sourceExpression.trim(), transform }), 400)
    return () => clearTimeout(t)
  }, [targetField, sourceExpression, transform])

  const check = useMappingCheck(profileId, { ...probe, transform: probe.transform || null, mappingId },
    !!probe.targetField && !!probe.sourceExpression)
  const valid = check.data?.valid ?? true

  useEffect(() => { onValidity(valid) }, [valid, onValidity])

  if (!check.data || (check.data.errors.length === 0 && check.data.warnings.length === 0)) return null
  return (
    <div className="space-y-1 text-xs" role="status" aria-live="polite">
      {check.data.errors.map((e) => (
        <p key={e} className="flex items-start gap-1.5 text-danger"><XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden="true" /><span className="sr-only">Error: </span>{e}</p>
      ))}
      {check.data.warnings.map((w) => (
        <p key={w} className="flex items-start gap-1.5 text-[hsl(var(--warning))]"><AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden="true" /><span className="sr-only">Warning: </span>{w}</p>
      ))}
    </div>
  )
}
