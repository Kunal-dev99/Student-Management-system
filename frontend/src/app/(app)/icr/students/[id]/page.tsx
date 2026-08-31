'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { IcrStudentPanel } from '@/features/icr/IcrStudentPanel'
import { useStudent } from '@/features/students/api'

export default function IcrStudentPage() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const q = useStudent(id)
  const title = q.data ? `${q.data.personName ?? q.data.studentRef} — ICR record` : 'ICR record'

  return (
    <>
      <PageHeader title={title}
        description="Clinical placement, independent tutor, bench fees and partner affiliations." />
      <div className="px-6 pb-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Link href="/icr/pathways" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Back to ICR pathways
          </Link>
          {q.data && (
            <Link href={`/students/${id}`} className="text-muted-foreground hover:text-foreground">
              Open core student record →
            </Link>
          )}
        </div>
        <IcrStudentPanel studentId={id} />
      </div>
    </>
  )
}
