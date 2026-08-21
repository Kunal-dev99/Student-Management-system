'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface Enterprise360Row {
  studentRef: string
  personName: string
  student: { status: string; studyMode: string; startDate: string | null }
  research: { topic: string | null; group: string | null; area: string | null }
  funding: { type: string; source: string | null; amount: string | null; currency: string | null } | null
  workforce: { isEmployee: boolean }
  statutory: { nationality: string | null; programme: string | null; expectedEnd: string | null }
}
export interface Enterprise360 {
  summary: { population: number; funded: number; employees: number; byStatus: Record<string, number> }
  lenses: string[]
  population: Enterprise360Row[]
}

export interface Analytics {
  risk: { atRiskCount: number; activeStudents: number; atRiskRatePct: number; students: { studentRef: string; personName: string; reasons: string[] }[] }
  completion: { completed: number; totalStudents: number; completionRatePct: number; avgTimeToCompletionDays: number | null }
  forecast: { onTrack: number; atRisk: number; note: string }
}

export const useEnterprise360 = () =>
  useQuery({ queryKey: ['enterprise360'], queryFn: () => api.get<Enterprise360>('/reports/pgr-enterprise-360') })

export const useAnalytics = () =>
  useQuery({ queryKey: ['analytics'], queryFn: () => api.get<Analytics>('/reports/analytics') })
