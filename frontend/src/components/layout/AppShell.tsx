'use client'

import { useEffect, useState, type ReactNode } from 'react'
import {
  LayoutDashboard,
  CheckSquare,
  Compass,
  Globe,
  Users,
  FlaskConical,
  Megaphone,
  FileCheck2,
  GraduationCap,
  UsersRound,
  Milestone,
  Wallet,
  BookOpenCheck,
  Award,
  Cable,
  Workflow,
  Settings,
  ScrollText,
  ShieldAlert,
  FileSpreadsheet,
  Sparkles,
} from 'lucide-react'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { Header } from '@/components/layout/header'
import { NotificationBell } from '@/components/notifications/NotificationBell'
import { AskPgrLauncher, AskPgrPalette } from '@/components/assistant/AskPgrPalette'
import { useAuth } from '@/shared/auth/AuthContext'

/**
 * PGR app shell — composes the design-system Sidebar + Header around the routed
 * page. Nav mirrors the backend capability modules (arch §7, §14.2).
 */
const mainNav: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/analytics', label: 'Analytics', icon: Globe },
  { href: '/portal', label: 'My journey', icon: Compass },
  { href: '/tasks', label: 'Tasks', icon: CheckSquare },
  { href: '/persons', label: 'Persons', icon: Users },
  { href: '/research', label: 'Research', icon: FlaskConical },
  { href: '/recruitment', label: 'Recruitment', icon: Megaphone },
  { href: '/admissions', label: 'Admissions', icon: FileCheck2 },
  { href: '/students', label: 'Students', icon: GraduationCap },
  { href: '/supervision', label: 'Supervision', icon: UsersRound },
  { href: '/progression', label: 'Progression', icon: Milestone },
  { href: '/funding', label: 'Funding', icon: Wallet },
  { href: '/thesis', label: 'Thesis', icon: BookOpenCheck },
  { href: '/completion', label: 'Completion', icon: Award },
]

const baseAdminNav: NavItem[] = [
  { href: '/workflows', label: 'Workflows', icon: Workflow },
  { href: '/integration', label: 'Integration', icon: Cable },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { principal, logout, hasPermission } = useAuth()
  const email = principal?.email ?? 'user@institution'
  const name = email.split('@')[0]
  const canAsk = hasPermission('assistant.use')
  const [paletteOpen, setPaletteOpen] = useState(false)

  // Cmd/Ctrl+K opens "Ask PGR" — but never while the user is typing somewhere else.
  useEffect(() => {
    if (!canAsk) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'k' || !(e.metaKey || e.ctrlKey)) return
      const el = document.activeElement as HTMLElement | null
      const typing =
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el?.isContentEditable
      if (typing && !paletteOpen) return
      e.preventDefault()
      setPaletteOpen((o) => !o)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canAsk, paletteOpen])

  // Nav is shaped by /api/v1/me. Hiding is convenience — the API still enforces.
  const adminNav: NavItem[] = [
    ...(hasPermission('funding.read')
      ? [{ href: '/funding-integrity', label: 'Funding integrity', icon: ShieldAlert }]
      : []),
    ...(hasPermission('reporting.read')
      ? [{ href: '/statutory', label: 'Statutory', icon: FileSpreadsheet }]
      : []),
    ...baseAdminNav,
    ...(hasPermission('audit.read')
      ? [{ href: '/audit', label: 'Audit', icon: ScrollText }]
      : []),
  ]

  // "Advanced" group — governed intelligence surfaces (Pattern Lab, ml.read).
  const advancedNav: NavItem[] = hasPermission('ml.read')
    ? [{ href: '/pattern-lab', label: 'Pattern Lab', icon: Sparkles }]
    : []

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        mainNav={mainNav}
        adminNav={adminNav}
        advancedNav={advancedNav}
        brandName="PGR Platform"
        brandTagline="Research Lifecycle"
        brandShort="PGR"
        brandHref="/dashboard"
        user={{ name, email }}
        onLogout={logout}
      />
      <div className="ml-64 transition-all duration-200">
        <Header
          title="PGR Platform"
          logoSrc="/brand/logo.png"
          logoAlt="Fusion Practices"
          onOpenPalette={canAsk ? () => setPaletteOpen(true) : undefined}
          actions={<NotificationBell />}
        />
        {/* Reserve space so the floating launcher never sits on top of page content. */}
        <main className={canAsk ? 'pb-24' : undefined}>{children}</main>
      </div>
      {canAsk && (
        <>
          {!paletteOpen && <AskPgrLauncher onClick={() => setPaletteOpen(true)} />}
          <AskPgrPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
        </>
      )}
    </div>
  )
}
