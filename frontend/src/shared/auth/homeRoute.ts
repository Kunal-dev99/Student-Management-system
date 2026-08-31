/**
 * Role-aware landing route. Each role's "home" is the screen that answers its
 * actual morning question: admins run the institution (dashboard), supervisors
 * run their caseload, executives read the dashboards, students see their journey.
 * Multi-role users land on the broadest surface they hold.
 */
export function homeRoute(roles: string[] | null | undefined): string {
  const r = roles ?? []
  if (r.includes('Institution Administrator') || r.includes('PGR Administrator')) return '/dashboard'
  if (r.includes('Supervisor')) return '/supervision'
  if (r.includes('Executive')) return '/dashboard'
  if (r.includes('Student')) return '/portal'
  return '/dashboard'
}
