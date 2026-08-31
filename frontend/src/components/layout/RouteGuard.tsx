'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ShieldOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/shared/auth/AuthContext'
import { canOpenRoute, findRouteAccess } from '@/shared/auth/routeAccess'
import { homeRoute } from '@/shared/auth/homeRoute'

/**
 * Blocks direct URL access to routes whose data the user cannot read, showing a
 * clean explanation instead of a page of erroring panels. Convenience only —
 * every endpoint still enforces its permission server-side.
 */
export function RouteGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? ''
  const { principal, hasPermission } = useAuth()

  const route = findRouteAccess(pathname)
  if (route && !canOpenRoute(route, hasPermission)) {
    const home = homeRoute(principal?.roles)
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <div className="max-w-md text-center space-y-3">
          <ShieldOff className="mx-auto h-10 w-10 text-muted-foreground" />
          <h2 className="text-lg font-semibold">This area isn&apos;t available for your role</h2>
          <p className="text-sm text-muted-foreground">
            Your account doesn&apos;t have access to this part of the platform. If you think you
            need it, ask an administrator.
          </p>
          <Button asChild size="sm" className="mt-2">
            <Link href={home}>Go to your home screen</Link>
          </Button>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
