import type { LucideIcon } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'

/** Placeholder for feature routes not yet built, so the shell is fully navigable. */
export function ComingSoon({
  title,
  description,
  icon,
  task,
}: {
  title: string
  description: string
  icon: LucideIcon
  task: string
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="px-6 pb-6">
        <PageSection icon={icon} title="Planned" accent="primary">
          <p className="text-helper">
            This module is scheduled in the delivery plan as{' '}
            <span className="font-mono text-xs">{task}</span>. The backend module and API land
            first, then this screen is wired to the typed client.
          </p>
        </PageSection>
      </div>
    </>
  )
}
