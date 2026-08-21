'use client'

import { Wallet } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useFundingSources } from '@/features/funding/api'

export default function FundingPage() {
  const { data, isLoading } = useFundingSources()
  return (
    <>
      <PageHeader title="Funding" description="Funding sources and arrangements." />
      <div className="px-6 pb-6 space-y-4">
        <p className="text-helper">
          Funding arrangements are held per student and tracked over time (a change closes the
          current arrangement and opens a new one). Manage them on a student’s page. Below are the
          funding sources available.
        </p>
        <PageSection icon={Wallet} title="Funding sources" accent="primary">
          {isLoading ? <Skeleton className="h-16 w-full" /> : data && data.length > 0 ? (
            <div className="space-y-2">
              {data.map((s) => (
                <div key={s.id} className="flex items-center gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <span className="text-sm font-medium">{s.name}</span>
                  {s.funderType && <Badge variant="secondary">{s.funderType.replace(/_/g, ' ')}</Badge>}
                </div>
              ))}
            </div>
          ) : <p className="text-helper">No funding sources configured.</p>}
        </PageSection>
      </div>
    </>
  )
}
