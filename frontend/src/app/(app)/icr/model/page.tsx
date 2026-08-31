'use client'

/**
 * ICR — the Institute of Cancer Research PGR model, and how this platform
 * carries it. Purely additive: a reference page plus pointers to the ICR
 * programmes/funders seeded into the existing engines (scripts/seed_icr.py).
 */

import Link from 'next/link'
import {
  Milestone, GitFork, UsersRound, Wallet, Building2, FlaskConical,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'

function Plat({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3 rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.06)] px-4 py-2.5 text-sm text-foreground/85">
      <span className="font-semibold text-[hsl(var(--info))]">In this platform: </span>
      {children}
    </div>
  )
}

function Gap({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2 rounded-md border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.07)] px-4 py-2.5 text-sm text-foreground/85">
      <span className="font-semibold text-[hsl(var(--warning))]">ICR module to build: </span>
      {children}
    </div>
  )
}

const PIPELINE = [
  ['Months 0–12', 'Provisional MPhil status'],
  ['Months 12–14', 'Transfer Viva (upgrade)'],
  ['Months 24 / 30', 'Progress reviews + data barrier'],
  ['Month 48', 'Final thesis submission'],
]

export default function IcrPage() {
  return (
    <>
      <PageHeader
        title="ICR — the Institute of Cancer Research model"
        description="How the ICR runs postgraduate research, and how this platform carries it."
      />
      <div className="px-6 pb-6 space-y-4">
        <p className="text-sm text-muted-foreground max-w-4xl">
          To understand the Postgraduate Research (PGR) model at the Institute of Cancer Research,
          look at it as an integrated pipeline: the ICR functions simultaneously as an academic
          school — awarding degrees via the{' '}
          <a className="text-primary hover:underline" href="https://www.icr.ac.uk/study-and-careers/phds-at-the-icr/phd-faqs-and-funding" target="_blank" rel="noreferrer">
            University of London
          </a>{' '}
          — and a high-volume laboratory workplace. Five pillars define the model.
        </p>

        <PageSection icon={Milestone} title="1 — The strict 4-year progress system" accent="primary">
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            {PIPELINE.map(([when, what], i) => (
              <span key={when} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-muted-foreground/50">→</span>}
                <span className="rounded-full border border-border bg-surface-2 px-3 py-1 text-xs">
                  <span className="font-mono text-muted-foreground">{when}</span>{' '}
                  <span className="font-medium">{what}</span>
                </span>
              </span>
            ))}
          </div>
          <ul className="list-disc pl-5 space-y-1.5 text-sm">
            <li><b>Provisional MPhil status (months 0–12):</b> no science student is admitted directly
              as a PhD candidate. Year one is probationary — onboarding, technical training, lab
              safety, baseline data collection.</li>
            <li><b>The Transfer Viva (months 12–14):</b> the most crucial filter in the system. The
              student submits a formal Upgrade Report (2,000–3,000 words: preliminary findings,
              literature review, explicit roadmap) and defends it in an oral exam before their
              supervisors and an appointed independent internal assessor. Success upgrades the
              registration to PhD status.</li>
            <li><b>Progression &amp; the 30-month barrier (months 24 &amp; 30):</b> regular monitoring
              by the ICR Academic Committees; at 30 months a rigorous check ensures sufficient raw,
              novel data for a viable thesis — minimising late-stage project failure.</li>
            <li><b>The 48-month hard limit:</b> a definitive thesis (up to 100,000 words) and a
              closed-door viva voce with one internal examiner and at least one external expert.</li>
          </ul>
          <Plat>
            This exact system is live as the <b>ICR PhD — Non-Clinical (4-year)</b> programme on the{' '}
            <Link href="/progression" className="text-primary hover:underline">Progression</Link> screen:
            five milestone definitions (+30d, +365d, +730d, +913d, +1460d), the Transfer Viva carrying its
            upgrade-report requirement and independent-assessor panel composition as structured data. Every
            ICR student registered on it gets these checkpoints generated automatically; panels, decisions,
            conditions and appeals reuse the existing progression engine unchanged.
          </Plat>
          <Gap>
            MPhil→PhD as a <i>registration status change</i> driven by the Transfer Viva outcome (today
            the upgrade is a decided milestone; the student&apos;s award target doesn&apos;t flip automatically),
            and a hard-stop warning as month 48 approaches.
          </Gap>
        </PageSection>

        <PageSection icon={GitFork} title="2 — Dual-pathway structuring (scientific vs clinical)" accent="accent">
          <ul className="list-disc pl-5 space-y-1.5 text-sm">
            <li><b>The Non-Clinical PhD track:</b> for science graduates (biochemistry, genetics, data
              science) — a 4-year full-time curriculum optimised for laboratory or computational
              project workloads.</li>
            <li><b>The Clinical MD(Res) / Clinical PhD track:</b> for practising doctors, surgeons and
              oncologists building translational-medicine careers. The MD(Res) is a condensed
              2-to-3-year model, merging real-time laboratory research with ongoing Specialist
              Registrar medical training.</li>
          </ul>
          <Plat>
            Both tracks exist as separate programmes with their own milestone clocks — the
            <b> ICR MD(Res) — Clinical (2–3 year)</b> programme carries the condensed schedule
            (+30d, +365d, +730d, +1095d hard limit). Study-mode changes and the part-time factor
            rescale a clinician&apos;s remaining registration when clinical duties shift.
          </Plat>
          <Gap>
            A &ldquo;clinical training overlay&rdquo;: recording the Specialist Registrar rotation
            alongside the studentship (the person model already supports concurrent dated identities —
            the same mechanism that holds student + employee today).
          </Gap>
        </PageSection>

        <PageSection icon={UsersRound} title="3 — The 360-degree supervisory ecosystem" accent="primary">
          <p className="text-sm mb-2">
            The ICR avoids placing student outcomes solely in the hands of a single lab leader.
            Responsibility splits into three layers:
          </p>
          <ul className="list-disc pl-5 space-y-1.5 text-sm">
            <li><b>Primary supervisor:</b> a Principal Investigator or Professor — directs the lab,
              secures its funding, sets the scientific direction.</li>
            <li><b>Secondary / co-supervisor:</b> complementary technical oversight — e.g. a wet-lab
              biologist paired with a computational genomics co-supervisor.</li>
            <li><b>Independent tutors &amp; Registry overseers:</b> senior tutors entirely outside the
              student&apos;s lab hierarchy — they conduct annual reviews and serve as a safe, neutral
              channel for disputes, stress or project deviation.</li>
          </ul>
          <Plat>
            The first two layers map directly onto the existing supervisor roles
            (<Badge variant="success">primary</Badge> <Badge variant="secondary">co-supervisor</Badge>{' '}
            <Badge variant="secondary">additional</Badge>), with capacity limits, dated relationships
            and the self-prioritising caseload. Independent assessors already appear as panel members
            on ICR milestones.
          </Plat>
          <Gap>
            A first-class <b>Independent Tutor</b> role: outside-the-lab constraint enforced at
            assignment (tutor&apos;s department ≠ student&apos;s lab), and a private tutor-notes channel
            separate from the supervision meeting log.
          </Gap>
        </PageSection>

        <PageSection icon={Wallet} title="4 — Fully funded, industrial-scale finance" accent="accent">
          <ul className="list-disc pl-5 space-y-1.5 text-sm">
            <li><b>Stipend delivery:</b> a highly competitive tax-free living allowance (typically
              £21,000+ per year) — research as a full-time professional commitment, no teaching burden
              or secondary employment.</li>
            <li><b>Protected bench fees:</b> the package covers University of London tuition and
              guarantees access to cash pools earmarked for heavy experimental spend — high-throughput
              sequencing, mass spectrometry, cell cultures.</li>
            <li><b>Diversified capital pillars:</b> seats funded by{' '}
              <a className="text-primary hover:underline" href="https://www.icr.ac.uk/about-us/icr-news/detail/icr-launches-new-phd-recruitment-drive" target="_blank" rel="noreferrer">
                Cancer Research UK (CRUK)
              </a>, the Medical Research Council (MRC), Breast Cancer Now, and targeted corporate
              partnerships.</li>
          </ul>
          <Plat>
            CRUK, MRC, Breast Cancer Now and a corporate-partnership pool are now{' '}
            <Link href="/funding" className="text-primary hover:underline">funding sources</Link>;
            stipends ride the existing arrangement + instalment-schedule machinery, awards link the
            money to its funder, and the nine integrity rules watch the whole chain — including
            &ldquo;funding ends before the 48-month clock does&rdquo;.
          </Plat>
          <Gap>
            <b>Bench fees as a tracked allocation</b>: a per-student experimental budget with draw-downs
            (sequencing runs, mass-spec time) beside the stipend — a new arrangement kind on the same
            bitemporal table.
          </Gap>
        </PageSection>

        <PageSection icon={Building2} title="5 — Multi-institutional convergence" accent="primary">
          <ul className="list-disc pl-5 space-y-1.5 text-sm">
            <li><b>The Royal Marsden NHS Foundation Trust:</b> students work on projects using
              real-world anonymised patient biopsies and data from active clinical trials happening
              next door.</li>
            <li><b>The Convergence Science Centre:</b> a combined training framework with Imperial
              College London — students split time across campuses, merging physical sciences
              (engineering, physics) with deep cancer biology.</li>
          </ul>
          <Plat>
            The person model&apos;s concurrent dated identities already carry &ldquo;student here,
            employee/honorary there&rdquo; without duplication, and the transactional outbox is the
            channel partner systems (NHS trust, Imperial) hear through — reliably, with reconciliation.
          </Plat>
          <Gap>
            A <b>partner-affiliation record</b> per student (Royal Marsden honorary contract, Imperial
            co-registration) with its own dates and compliance flags (e.g. NHS research passport),
            surfaced on the student record and the HESA return.
          </Gap>
        </PageSection>

        <PageSection icon={FlaskConical} title="How to see it working today" accent="success">
          <ol className="list-decimal pl-5 space-y-1.5 text-sm">
            <li>Open <Link href="/progression" className="text-primary hover:underline">Progression</Link>{' '}
              and pick <b>ICR PhD — Non-Clinical (4-year)</b>: the five ICR checkpoints, with the
              Transfer Viva&apos;s document and panel requirements.</li>
            <li>Register a student on that programme — their milestones (Transfer Viva at +12 months,
              the 30-month barrier, the 48-month limit) generate automatically, and the Journey tracker
              renders the ICR pipeline live.</li>
            <li>Open <Link href="/funding" className="text-primary hover:underline">Funding</Link>:
              CRUK, MRC and Breast Cancer Now are selectable sources for any new arrangement.</li>
          </ol>
          <p className="text-helper mt-2">
            Everything above was added without modifying existing code: two programmes, nine milestone
            definitions and four funding sources riding the engines the rest of the platform already uses
            (<code className="font-mono text-xs">backend/scripts/seed_icr.py</code>).
          </p>
        </PageSection>
      </div>
    </>
  )
}
