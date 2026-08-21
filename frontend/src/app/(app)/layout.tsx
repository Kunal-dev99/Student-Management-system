import type { ReactNode } from 'react'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { AppShell } from '@/components/layout/AppShell'

export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  )
}
