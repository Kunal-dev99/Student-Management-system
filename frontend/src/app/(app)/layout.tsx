import type { ReactNode } from 'react'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { AppShell } from '@/components/layout/AppShell'
import { RouteGuard } from '@/components/layout/RouteGuard'

export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>
        <RouteGuard>{children}</RouteGuard>
      </AppShell>
    </AuthGuard>
  )
}
