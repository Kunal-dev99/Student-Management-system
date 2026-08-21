'use client'

import { Milestone as MilestoneIcon } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useMilestoneDefinitions, useProgrammes } from '@/features/progression/api'

function ProgrammeDefinitions({ programmeId, name }: { programmeId: string; name: string }) {
  const { data, isLoading } = useMilestoneDefinitions(programmeId)
  return (
    <PageSection icon={MilestoneIcon} title={name} accent="primary">
      {isLoading ? <Skeleton className="h-16 w-full" /> : data && data.length > 0 ? (
        <ol className="relative border-l border-border ml-2 space-y-3">
          {data.map((d) => (
            <li key={d.id} className="ml-4">
              <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{d.name}</span>
                <Badge variant="secondary">{d.dueOffsetDays} days after start</Badge>
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="text-helper">No milestone definitions configured for this programme.</p>}
    </PageSection>
  )
}

export default function ProgressionPage() {
  const { data: programmes, isLoading } = useProgrammes()
  return (
    <>
      <PageHeader title="Progression" description="Configurable milestone flows per programme." />
      <div className="px-6 pb-6 space-y-4">
        <p className="text-helper">
          These are the milestone definitions each programme runs. A student’s milestones are
          generated from them; record submissions and panel decisions on the student’s page.
        </p>
        {isLoading && <Skeleton className="h-24 w-full" />}
        {programmes?.map((p) => <ProgrammeDefinitions key={p.id} programmeId={p.id} name={p.name} />)}
        {programmes && programmes.length === 0 && <p className="text-helper">No programmes yet.</p>}
      </div>
    </>
  )
}
