'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
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
  Receipt,
  BookOpenCheck,
  Award,
  TrendingUp,
  Cable,
  Workflow,
  Settings,
  ScrollText,
  ShieldAlert,
  FileSpreadsheet,
  Sparkles,
  Wand2,
  FileText,
  MessageSquare,
  GitCompare,
} from 'lucide-react'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { Header } from '@/components/layout/header'
import { NotificationBell } from '@/components/notifications/NotificationBell'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { useTenant } from '@/shared/tenant/useTenant'
import { AskPgrLauncher, AskPgrPalette } from '@/components/assistant/AskPgrPalette'
import { useAuth } from '@/shared/auth/AuthContext'
import { homeRoute } from '@/shared/auth/homeRoute'
import { canSeeRoute, findRouteAccess } from '@/shared/auth/routeAccess'

/**
 * PGR app shell — composes the design-system Sidebar + Header around the routed
 * page. Nav mirrors the backend capability modules (arch §7, §14.2).
 */
const mainNav: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/analytics', label: 'Analytics', icon: Globe },
  { href: '/portal', label: 'My journey', icon: Compass },
  { href: '/documents', label: 'Documents', icon: FileText },
  { href: '/messages', label: 'Messages', icon: MessageSquare },
  { href: '/tasks', label: 'Tasks', icon: CheckSquare },
  { href: '/reviews/weekly', label: 'Weekly review', icon: Sparkles },
  { href: '/my-students', label: 'My students', icon: UsersRound },
  { href: '/persons', label: 'Persons', icon: Users },
  { href: '/research', label: 'Research', icon: FlaskConical },
  { href: '/recruitment', label: 'Recruitment', icon: Megaphone },
  { href: '/admissions', label: 'Admissions', icon: FileCheck2 },
  { href: '/students', label: 'Students', icon: GraduationCap },
  { href: '/supervision', label: 'Supervision', icon: UsersRound },
  { href: '/supervision/workforce', label: 'Workforce', icon: UsersRound },
  { href: '/progression', label: 'Progression', icon: Milestone },
  { href: '/progression/transfer-viva', label: 'Transfer viva', icon: TrendingUp },
  { href: '/funding', label: 'Funding', icon: Wallet },
  { href: '/funding/payments', label: 'Payment status', icon: Receipt },
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
  const tenant = useTenant()
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

  // Nav is driven by the central route-access map (shared/auth/routeAccess.ts):
  // a route appears only when the role may see it AND the permissions its data
  // needs are held. Hiding is convenience — the API still enforces server-side.
  // Memoised on the permission bag — recomputing on every click made every nav item
  // run findRouteAccess again for no reason, adding a perceptible frame stall.
  const roles = principal?.roles ?? []
  const { filteredMainNav, adminNav, advancedNav } = useMemo(() => {
    const visible = (items: NavItem[]) =>
      items.filter((item) => {
        const route = findRouteAccess(item.href)
        return !route || canSeeRoute(route, roles, hasPermission)
      })
    return {
      filteredMainNav: visible(mainNav),
      adminNav: visible([
        { href: '/funding-integrity', label: 'Funding integrity', icon: ShieldAlert },
        { href: '/statutory', label: 'Statutory', icon: FileSpreadsheet },
        ...baseAdminNav,
        { href: '/audit', label: 'Audit', icon: ScrollText },
      ]),
      advancedNav: visible([
        { href: '/composer', label: 'Composer', icon: Wand2 },
        { href: '/pattern-lab', label: 'Pattern Lab', icon: Sparkles },
        { href: '/case-explorer', label: 'Case Explorer', icon: Compass },
        { href: '/policy-compiler', label: 'Policy Compiler', icon: GitCompare },
        { href: '/change-radar', label: 'Change Radar', icon: FileText },
      ]),
    }
    // `roles.join` gives a stable dep instead of the fresh array reference each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles.join(','), hasPermission])

  // Stable callback identities — otherwise Header/Launcher get a fresh function on every
  // AppShell render and can't skip their own re-renders even if they're memoised.
  const openPalette = useCallback(() => setPaletteOpen(true), [])
  const onOpenPalette = canAsk ? openPalette : undefined

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        mainNav={filteredMainNav}
        adminNav={adminNav}
        advancedNav={advancedNav}
        brandName={tenant?.name ?? 'PGR Platform'}
        brandTagline={tenant?.tagline ?? 'Research Lifecycle'}
        brandShort={tenant?.logoText ?? 'PGR'}
        brandBadge={tenant?.logoText ?? 'PGR'}
        brandColor={tenant?.primaryColor ?? undefined}
        brandHref={homeRoute(roles)}
        user={{ name, email }}
        onLogout={logout}
      />
      <div className="ml-64 transition-all duration-200">
        <Header
          title="PGR Platform"
          logoSrc="/brand/logo.png"
          logoAlt="Fusion Practices"
          onOpenPalette={onOpenPalette}
          actions={<><LanguageSwitcher /><NotificationBell /></>}
        />
        {/* Reserve space so the floating launcher never sits on top of page content. */}
        <main className={canAsk ? 'pb-24' : undefined}>{children}</main>
      </div>
      {canAsk && (
        <>
          {!paletteOpen && <AskPgrLauncher onClick={openPalette} />}
          <AskPgrPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
        </>
      )}
    </div>
  )
}
