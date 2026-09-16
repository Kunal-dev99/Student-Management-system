/**
 * Single source of truth for which routes each user can SEE (nav) and OPEN (guard).
 *
 * Two dimensions, deliberately separate:
 * - `perms`: permission codes (ANY-of) the route's data actually requires. This is
 *   the hard requirement — RouteGuard blocks direct URL access without it.
 * - `roles`: optional visibility refinement for routes whose permission is held
 *   more broadly than the audience. Example: students hold student.read (row-scoped
 *   to themselves), but the Students register is an office surface — so the route
 *   is visible only to the roles listed, even though the permission alone would pass.
 *
 * A route with `perms: []` needs authentication only.
 * Hiding/guarding here is convenience — every endpoint still enforces server-side.
 */

export const ADMIN_ROLES = ['Institution Administrator', 'PGR Administrator']

export interface RouteAccess {
  href: string
  /** ANY-of permission codes required to open the route. Empty = authenticated only. */
  perms: string[]
  /** When set, the route only appears in nav (and opens) for these roles. */
  roles?: string[]
}

export const ROUTE_ACCESS: RouteAccess[] = [
  // Main
  { href: '/dashboard', perms: ['reporting.read'] },
  { href: '/analytics', perms: ['reporting.read'] },
  // "My journey" is the student's own portal — an admin has no lifecycle to look at.
  // Same for the supervisor: they're personally-scoped surfaces. If an admin needs to
  // see what a student sees, they log in as one.
  { href: '/portal', perms: [], roles: ['Student'] },
  { href: '/documents', perms: [], roles: ['Student'] },
  { href: '/messages', perms: [], roles: ['Student', 'Supervisor'] },
  { href: '/tasks', perms: [], roles: [...ADMIN_ROLES, 'Supervisor', 'Student'] },
  { href: '/persons', perms: ['person.read'] },
  { href: '/research', perms: ['recruitment.read'] },
  { href: '/recruitment', perms: ['recruitment.read'] },
  { href: '/admissions', perms: ['recruitment.read'] },
  { href: '/students', perms: ['student.read'], roles: ADMIN_ROLES },
  { href: '/supervision', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  { href: '/supervision/requests', perms: ['student.read'], roles: ADMIN_ROLES },
  { href: '/supervision/workforce', perms: ['student.read'], roles: ADMIN_ROLES },
  { href: '/progression', perms: ['progression.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  { href: '/funding', perms: ['funding.read'], roles: ADMIN_ROLES },
  { href: '/funding/payments', perms: ['funding.read'], roles: ADMIN_ROLES },
  { href: '/thesis', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  { href: '/completion', perms: ['student.read'], roles: ADMIN_ROLES },
  // ICR module — institution-specific group, additive to the core workspace.
  { href: '/progression/transfer-viva', perms: ['progression.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // Administration
  { href: '/funding-integrity', perms: ['funding.read'], roles: ADMIN_ROLES },
  { href: '/statutory', perms: ['reporting.read'], roles: ADMIN_ROLES },
  { href: '/programmes', perms: ['admin.configure'], roles: ADMIN_ROLES },
  { href: '/workflows', perms: ['admin.configure'] },
  { href: '/integration', perms: ['admin.configure'] },
  { href: '/settings', perms: [] },
  { href: '/settings/assistant', perms: ['admin.configure'], roles: ADMIN_ROLES },
  { href: '/audit', perms: ['audit.read'], roles: ADMIN_ROLES },
  // Advanced
  { href: '/pattern-lab', perms: ['ml.read'], roles: ADMIN_ROLES },
  // The composer reads whatever the caller may read — its own function catalogue is
  // permission-filtered server-side, so student.read is the right floor.
  { href: '/composer', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // AI-as-a-layer surface — same permission floor as any risk view.
  { href: '/reviews', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // Institutional Memory — comparable case explorer. Same floor as any student view;
  // it never surfaces more than a supervisor or admin could already see per-case.
  { href: '/case-explorer', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // Policy Compiler — governed configuration proposals. Same floor as /workflows,
  // /integration and other admin.configure surfaces.
  { href: '/policy-compiler', perms: ['admin.configure'], roles: ADMIN_ROLES },
  // Research Change Radar — document comparison. Matches the backend's own
  // require_permission("document.read") floor.
  { href: '/change-radar', perms: ['document.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // Supervisor's own caseload — the "who needs me today?" landing. Personally scoped,
  // so admins don't see it either — they use /students and /supervision/workforce.
  { href: '/my-students', perms: [], roles: ['Supervisor'] },
]

/**
 * Configurable-navigation routes (the runtime park mechanism). Mirrors the backend
 * `settings/nav_features.py` registry: every toggleable sidebar destination. A disabled one is
 * hidden from the nav and blocked on direct URL. Recruitment funnel routes are governed by the
 * separate `recruitment.enabled` flag and are intentionally absent here.
 */
export const NAV_ROUTES: string[] = [
  '/dashboard', '/analytics', '/portal', '/documents', '/messages', '/tasks', '/reviews/weekly',
  '/my-students', '/persons', '/students', '/funding/payments', '/supervision',
  '/supervision/workforce', '/progression', '/progression/transfer-viva', '/funding', '/thesis',
  '/completion', '/programmes', '/funding-integrity', '/statutory', '/workflows', '/integration',
  '/settings', '/audit', '/composer', '/pattern-lab', '/case-explorer', '/policy-compiler',
  '/change-radar',
]

/** The most specific nav route that owns this path (longest-prefix), for the nav-feature check. */
export function navRouteForPath(pathname: string): string | undefined {
  let best: string | undefined
  for (const r of NAV_ROUTES) {
    if (pathname === r || pathname.startsWith(r + '/')) {
      if (!best || r.length > best.length) best = r
    }
  }
  return best
}

/** Longest-prefix match so detail routes (/students/{id}) inherit their list route's rules. */
export function findRouteAccess(pathname: string): RouteAccess | undefined {
  let best: RouteAccess | undefined
  for (const r of ROUTE_ACCESS) {
    if (pathname === r.href || pathname.startsWith(r.href + '/')) {
      if (!best || r.href.length > best.href.length) best = r
    }
  }
  return best
}

/**
 * Can the route be OPENED (RouteGuard)? Permissions only — roles never block
 * access, because e.g. a supervisor opens /students/{id} from their caseload
 * even though the Students register isn't in their nav. Row-scoping on the
 * server protects the data itself.
 */
export function canOpenRoute(
  route: RouteAccess,
  hasPermission: (code: string) => boolean,
): boolean {
  return route.perms.length === 0 || route.perms.some(hasPermission)
}

/** Should the route appear in this user's NAV? Role visibility + permissions. */
export function canSeeRoute(
  route: RouteAccess,
  roles: string[],
  hasPermission: (code: string) => boolean,
): boolean {
  if (route.roles && !route.roles.some((r) => roles.includes(r))) return false
  return canOpenRoute(route, hasPermission)
}
