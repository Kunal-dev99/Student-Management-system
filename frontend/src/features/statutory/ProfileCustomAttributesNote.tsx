'use client'

/**
 * One line above a return's fields (custom attribute governance, Phase 5): which custom
 * attributes this return reads — the only ones loaded when it is generated — which of those are
 * obsolete, and which live attributes it doesn't use. Hidden when the institution has none.
 */
import { useProfileCustomAttributes } from '@/features/statutory/api'

export function ProfileCustomAttributesNote({ profileId }: { profileId: string }) {
  const { data } = useProfileCustomAttributes(profileId)
  if (!data || (data.used.length === 0 && data.unusedLive.length === 0)) return null
  return (
    <p className="mb-3 text-helper">
      <span className="font-medium text-foreground">Custom attributes in this return:</span>{' '}
      {data.used.length === 0 ? 'none' : data.used.map((u) => (
        <span key={u.mappingId} className={u.obsolete ? 'text-danger' : undefined}>
          <span className="font-mono text-xs">{u.customKey}</span> → {u.targetField}{u.obsolete ? ' (no longer live)' : ''}
          {' '}
        </span>
      ))}
      — only these are read when the return is generated.
      {data.unusedLive.length > 0 && (
        <> Not used here: <span className="font-mono text-xs">{data.unusedLive.join(', ')}</span>.</>
      )}
    </p>
  )
}
