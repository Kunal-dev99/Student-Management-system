'use client'

import type { ReactNode } from 'react'
import {
  LayoutDashboard,
  CheckSquare,
  Compass,
  Globe,
  Users,
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
} from 'lucide-react'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { Header } from '@/components/layout/header'
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
  { href: '/recruitment', label: 'Recruitment', icon: Megaphone },
  { href: '/admissions', label: 'Admissions', icon: FileCheck2 },
  { href: '/students', label: 'Students', icon: GraduationCap },
  { href: '/supervision', label: 'Supervision', icon: UsersRound },
  { href: '/progression', label: 'Progression', icon: Milestone },
  { href: '/funding', label: 'Funding', icon: Wallet },
  { href: '/thesis', label: 'Thesis', icon: BookOpenCheck },
  { href: '/completion', label: 'Completion', icon: Award },
]

const adminNav: NavItem[] = [
  { href: '/workflows', label: 'Workflows', icon: Workflow },
  { href: '/integration', label: 'Integration', icon: Cable },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { principal, logout } = useAuth()
  const email = principal?.email ?? 'user@institution'
  const name = email.split('@')[0]

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        mainNav={mainNav}
        adminNav={adminNav}
        brandName="PGR Platform"
        brandTagline="Research Lifecycle"
        brandShort="PGR"
        brandHref="/dashboard"
        user={{ name, email }}
        onLogout={logout}
      />
      <div className="ml-64 transition-all duration-200">
        <Header title="PGR Platform" logoSrc="/brand/logo.png" logoAlt="Fusion Practices" />
        <main>{children}</main>
      </div>
    </div>
  )
}
