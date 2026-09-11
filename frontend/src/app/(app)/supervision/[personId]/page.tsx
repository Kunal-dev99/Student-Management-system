'use client'

/**
 * W2 — Supervisor profile page. Edit max_students, availability, sabbatical dates, bio.
 */

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, ArrowUpRight, GraduationCap, UserRound } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { usePerson } from '@/features/persons/api'
import { useCaseload } from '@/features/supervision/api'
import {
  useSupervisorProfile, useUpsertSupervisorProfile,
  type SupervisorAvailability,
} from '@/features/supervision/w2_api'

export default function SupervisorProfilePage() {
  const params = useParams<{ personId: string }>()
  const personId = params.personId
  const { toast } = useToast()
  const q = useSupervisorProfile(personId)
  const save = useUpsertSupervisorProfile(personId)
  const person = usePerson(personId)
  const caseload = useCaseload(personId)
  const supervisorName = person.data
    ? `${person.data.givenName} ${person.data.familyName}`
    : ''

  const [maxStudents, setMaxStudents] = useState('8')
  const [availability, setAvailability] = useState<SupervisorAvailability>('available')
  const [acceptingNew, setAcceptingNew] = useState(true)
  const [sabbaticalFrom, setSabbaticalFrom] = useState('')
  const [sabbaticalTo, setSabbaticalTo] = useState('')
  const [bio, setBio] = useState('')

  useEffect(() => {
    const p = q.data?.profile
    if (p) {
      setMaxStudents(String(p.maxStudents))
      setAvailability(p.availability)
      setAcceptingNew(p.acceptingNew)
      setSabbaticalFrom(p.sabbaticalFrom ?? '')
      setSabbaticalTo(p.sabbaticalTo ?? '')
      setBio(p.bio ?? '')
    }
  }, [q.data])

  const submit = async () => {
    try {
      await save.mutateAsync({
        maxStudents: parseInt(maxStudents, 10),
        availability,
        acceptingNew,
        sabbaticalFrom: sabbaticalFrom || null,
        sabbaticalTo: sabbaticalTo || null,
        bio,
      })
      toast({ title: 'Profile saved' })
    } catch (e) { toast({ title: 'Save failed', description: (e as ApiError).message, variant: 'destructive' }) }
  }

  return (
    <>
      <PageHeader
        title={supervisorName || 'Supervisor profile'}
        description={supervisorName
          ? `Supervisor profile · max students, availability, sabbatical, and current caseload.`
          : 'Max students, availability, sabbatical window, research areas.'}
      />
      <div className="px-6 pb-6 space-y-4">
        <Link href="/supervision/workforce" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to workforce
        </Link>

        <PageSection icon={UserRound} title="Profile" accent="primary">
          {q.isLoading ? <Skeleton className="h-32 w-full" /> : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={availability === 'available' ? 'success'
                              : availability === 'full' ? 'warning' : 'secondary'}>
                  {availability.replace(/_/g,' ')}
                </Badge>
                {acceptingNew ? <Badge variant="secondary">accepting new</Badge>
                              : <Badge variant="outline">not accepting new</Badge>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="max">Max students</Label>
                  <Input id="max" type="number" min={0} max={30} value={maxStudents}
                    onChange={(e) => setMaxStudents(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Availability</Label>
                  <Select value={availability} onValueChange={(v) => setAvailability(v as SupervisorAvailability)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="available">available</SelectItem>
                      <SelectItem value="full">full</SelectItem>
                      <SelectItem value="on_leave">on leave</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="acc" checked={acceptingNew}
                  onCheckedChange={(v) => setAcceptingNew(v === true)} />
                <Label htmlFor="acc">Accepting new supervisees</Label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="sf">Sabbatical from</Label>
                  <Input id="sf" type="date" value={sabbaticalFrom} onChange={(e) => setSabbaticalFrom(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="st">Sabbatical to</Label>
                  <Input id="st" type="date" value={sabbaticalTo} onChange={(e) => setSabbaticalTo(e.target.value)} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bio">Bio</Label>
                <Textarea id="bio" className="min-h-[80px]" value={bio}
                  onChange={(e) => setBio(e.target.value)} placeholder="Research interests, availability caveats…" />
              </div>
              <div>
                <Button size="sm" onClick={submit} disabled={save.isPending}>
                  {save.isPending ? 'Saving…' : 'Save profile'}
                </Button>
                <span className="ml-3 text-helper">
                  When set, this profile&apos;s max students wins over the institution-wide setting.
                </span>
              </div>
            </div>
          )}
        </PageSection>

        <PageSection
          icon={GraduationCap}
          title={`Current caseload${caseload.data ? ` (${caseload.data.length})` : ''}`}
          accent="primary"
          description="Students this supervisor is currently supervising. Meetings shown to spot supervision gaps."
        >
          {caseload.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (caseload.data ?? []).length === 0 ? (
            <p className="text-helper">No active supervisees.</p>
          ) : (
            <ul className="divide-y divide-border/50 rounded-md border border-border/50">
              {(caseload.data ?? []).map((c) => (
                <li key={c.relationshipId} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0 space-y-0.5">
                    <Link
                      href={`/students/${c.studentId}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                      {c.personName}
                      <ArrowUpRight className="h-3.5 w-3.5" />
                    </Link>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{c.studentRef}</span>
                      <Badge variant="outline">{c.role.replace(/_/g, ' ')}</Badge>
                    </div>
                  </div>
                  <div className="text-right">
                    {c.meetingOverdue
                      ? <Badge variant="warning">meetings overdue</Badge>
                      : <Badge variant="success">up to date</Badge>}
                    <p className="text-helper num mt-0.5">
                      last {c.lastMeetingOn ?? '—'}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </PageSection>
      </div>
    </>
  )
}
