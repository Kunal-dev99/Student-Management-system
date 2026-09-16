'use client'

/**
 * Programmes — top-level academic-structure admin (ICR G3, promoted out of Settings).
 *
 * Create and edit programmes, their milestone templates and (for taught programmes)
 * the grading policy. Previously a Settings tab; lifted to its own nav page because
 * admins didn't discover it buried under Settings. Still `admin.configure` gated —
 * RouteGuard blocks direct access and every endpoint enforces server-side.
 */
import { PageHeader } from '@/components/common/PageHeader'
import { ProgrammesTab } from '@/features/settings/ProgrammesTab'

export default function ProgrammesPage() {
  return (
    <div>
      <PageHeader
        title="Programmes"
        description="Programme records, milestone templates and taught grading policy."
      />
      <div className="px-6 pb-6">
        <ProgrammesTab />
      </div>
    </div>
  )
}
