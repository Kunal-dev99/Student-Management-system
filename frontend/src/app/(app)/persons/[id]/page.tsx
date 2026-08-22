'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, User, Activity } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Skeleton } from '@/components/ui/skeleton'
import { usePerson, usePersonTimeline } from '@/features/persons/api'
import { IdentitiesSection } from '@/features/persons/IdentitiesSection'

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-label">{label}</p>
      <p className="text-sm mt-0.5">{value || '—'}</p>
    </div>
  )
}

export default function PersonDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const person = usePerson(id)
  const timeline = usePersonTimeline(id)

  const p = person.data
  const title = p ? `${p.givenName} ${p.familyName}` : 'Person'

  return (
    <>
      <PageHeader title={title} description="Person 360 — profile, identities, and lifecycle." />
      <div className="px-6 pb-6 space-y-4">
        <Link href="/persons" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to persons
        </Link>

        <PageSection icon={User} title="Profile" accent="primary">
          {person.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : person.isError ? (
            <p className="text-[hsl(var(--destructive))]">{(person.error as Error)?.message}</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Field label="Given name" value={p?.givenName} />
              <Field label="Family name" value={p?.familyName} />
              <Field label="Preferred name" value={p?.preferredName} />
              <Field label="Email" value={p?.email} />
              <Field label="Nationality" value={p?.nationality} />
              <Field label="Date of birth" value={p?.dateOfBirth} />
            </div>
          )}
        </PageSection>

        <IdentitiesSection personId={id} />

        <PageSection icon={Activity} title="Lifecycle timeline" accent="primary">
          {timeline.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : timeline.data?.entries.length ? (
            <ol className="relative border-l border-border ml-2 space-y-4">
              {timeline.data.entries.map((e, i) => (
                <li key={i} className="ml-4">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
                  <p className="text-sm font-medium">{e.label}</p>
                  <p className="text-helper num">{e.at}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-helper">
              No lifecycle events yet. As recruitment, student record, funding, and thesis modules
              land, this timeline fills in across the person’s identities.
            </p>
          )}
        </PageSection>
      </div>
    </>
  )
}
