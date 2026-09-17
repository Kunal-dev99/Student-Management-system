'use client'

/**
 * Mid-term programme transfer — read-only preview of what will change if the request is
 * approved. Rendered inside the "Request…" dialog once a target programme + effective date
 * are chosen. Everything here is computed deterministically from the target programme's
 * definition and the student's current milestones/enrolments; the approval endpoint does
 * the real work and returns the same figures back.
 */

import { AlertTriangle, ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useMilestones } from '@/features/progression/api'
import { useTaughtRecord } from '@/features/taught/api'
import type { ProgrammeDetail } from '@/features/programmes/api'

const DAY = 86_400_000

function addMonthsIso(iso: string, months: number): string {
  const d = new Date(iso + 'T00:00:00Z')
  const day = d.getUTCDate()
  d.setUTCMonth(d.getUTCMonth() + months)
  // Guard month roll-over (e.g. Jan 31 + 1 month => Feb 28/29, not Mar 3).
  if (d.getUTCDate() < day) d.setUTCDate(0)
  return d.toISOString().slice(0, 10)
}

export function ProgrammeChangeImpactView({
  studentId,
  currentProgramme,
  newProgramme,
  currentExpectedEnd,
  effectiveDate,
}: {
  studentId: string
  currentProgramme: ProgrammeDetail | null
  newProgramme: ProgrammeDetail
  currentExpectedEnd: string | null
  effectiveDate: string
}) {
  const milestonesQ = useMilestones(studentId)
  const wasTaught = currentProgramme?.programmeType === 'taught'
  const taughtQ = useTaughtRecord(studentId, wasTaught)

  // Milestones the approval will cancel — anything not yet decided or already cancelled.
  const undecided = (milestonesQ.data ?? []).filter(
    (m) => m.status !== 'decided' && !/superseded by programme change/.test(m.name),
  )

  const projectedEnd = newProgramme.durationMonths
    ? addMonthsIso(effectiveDate, newProgramme.durationMonths)
    : null
  const delta = (currentExpectedEnd && projectedEnd)
    ? Math.round((Date.parse(projectedEnd) - Date.parse(currentExpectedEnd)) / DAY)
    : null

  const crossType =
    !!currentProgramme && currentProgramme.programmeType !== newProgramme.programmeType

  const takenModules = (taughtQ.data?.enrolments ?? []).filter(
    (e) => e.status === 'completed' || e.moduleMark != null,
  )

  return (
    <div className="rounded-md border border-border bg-muted/30 p-3 space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <p className="font-medium">Impact preview</p>
        <Badge variant="secondary" className="text-xs">read-only</Badge>
      </div>

      {crossType && (
        <div className="rounded-md border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.1)] p-2.5 text-sm flex gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 text-[hsl(var(--warning))] shrink-0" />
          <div>
            <p className="font-medium text-[hsl(var(--warning))]">
              Cross-type transfer — {currentProgramme?.programmeType} to {newProgramme.programmeType}
            </p>
            <p className="text-muted-foreground mt-0.5">
              The two programmes run different lifecycles (thesis vs modules).{' '}
              {currentProgramme?.programmeType === 'taught'
                ? 'Taught modules already taken and any dissertation progress stay on the record but may need Registry review for credit transfer.'
                : 'Thesis progress and supervisor relationships stay on the record but may need Registry review under the new programme structure.'}
            </p>
          </div>
        </div>
      )}

      {/* Expected end */}
      <div>
        <p className="text-label">Expected end</p>
        <div className="flex flex-wrap items-baseline gap-2 mt-0.5">
          <span className="num text-muted-foreground line-through">{currentExpectedEnd ?? '—'}</span>
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="num font-semibold">{projectedEnd ?? '—'}</span>
          {delta !== null && (
            <Badge variant={delta > 0 ? 'warning' : delta < 0 ? 'success' : 'secondary'}>
              {delta > 0 ? '+' : ''}{delta} day{Math.abs(delta) === 1 ? '' : 's'}
            </Badge>
          )}
        </div>
        {newProgramme.durationMonths == null && (
          <p className="text-helper mt-0.5">
            The new programme has no configured duration — the expected end date will need to
            be set manually after approval.
          </p>
        )}
      </div>

      {/* Programme type */}
      <div>
        <p className="text-label">Programme type</p>
        <div className="flex items-center gap-2 mt-1">
          <Badge variant="outline">{currentProgramme?.programmeType ?? 'unknown'}</Badge>
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
          <Badge variant={crossType ? 'warning' : 'outline'}>{newProgramme.programmeType}</Badge>
        </div>
      </div>

      {/* Milestones */}
      <div>
        <p className="text-label">Milestones</p>
        <p className="text-muted-foreground mt-0.5">
          {milestonesQ.isLoading
            ? 'Checking current schedule…'
            : (
              <>
                {undecided.length} undecided milestone{undecided.length === 1 ? '' : 's'} on
                the current schedule will be cancelled; the new programme&apos;s schedule
                will be generated from {effectiveDate}. Milestones already decided stay on
                the record as historical facts.
              </>
            )}
        </p>
      </div>

      {/* Supervisors + funding — neutral note. */}
      <div>
        <p className="text-label">Supervisors &amp; funding</p>
        <p className="text-muted-foreground mt-0.5">
          Carry over unchanged — both are student-scoped, not programme-scoped. Review
          whether they remain appropriate under the new programme.
        </p>
      </div>

      {/* Taught modules already taken — only relevant if the current programme is taught. */}
      {wasTaught && takenModules.length > 0 && (
        <div>
          <p className="text-label">Taught modules already taken</p>
          <p className="text-muted-foreground mt-0.5 mb-1.5">
            Stay on the record. Whether credit transfers into the new programme is a
            Registry decision.
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {takenModules.map((e) => (
              <li key={e.id}>
                <Badge variant="outline" className="font-mono text-xs">
                  {e.moduleCode ?? e.moduleId.slice(0, 6)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
