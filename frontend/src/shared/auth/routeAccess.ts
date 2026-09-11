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
  { href: '/thesis', perms: ['student.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  { href: '/completion', perms: ['student.read'], roles: ADMIN_ROLES },
  // ICR module — institution-specific group, additive to the core workspace.
  { href: '/progression/transfer-viva', perms: ['progression.read'], roles: [...ADMIN_ROLES, 'Supervisor'] },
  // Administration
  { href: '/funding-integrity', perms: ['funding.read'], roles: ADMIN_ROLES },
  { href: '/statutory', perms: ['reporting.read'], roles: ADMIN_ROLES },
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
  // Supervisor's own caseload — the "who needs me today?" landing. Personally scoped,
  // so admins don't see it either — they use /students and /supervision/workforce.
  { href: '/my-students', perms: [], roles: ['Supervisor'] },
]

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
