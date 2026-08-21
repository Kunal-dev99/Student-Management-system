'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface ExecutiveDashboard {
  totals: { persons: number; students: number; applications: number; opportunities: number }
  activeResearchers: number
  completions: number
  conversionRatePct: number
  applicationsInPipeline: number
  fundedStudents: number
  thesesSubmitted: number
  thesesApproved: number
  applicationsByStage: Record<string, number>
  studentsByStatus: Record<string, number>
}

export interface AdministratorDashboard {
  applicationsAwaitingAssessment: number
  offersAwaitingAcceptance: number
  progressionReviewsDue: number
  milestonesOverdue: number
  thesesSubmitted: number
  pipelineByStage: Record<string, number>
}

export const useExecutiveDashboard = () =>
  useQuery({ queryKey: ['dashboard', 'executive'], queryFn: () => api.get<ExecutiveDashboard>('/dashboards/executive') })

export const useAdministratorDashboard = () =>
  useQuery({ queryKey: ['dashboard', 'administrator'], queryFn: () => api.get<AdministratorDashboard>('/dashboards/administrator') })

export interface SupervisorCaseloadItem {
  studentId: string
  studentRef: string
  personName: string
  status: string
  currentMilestone: string | null
  milestoneStatus: string | null
  funding: 'active' | 'none'
  risk: boolean
  riskReasons: string[]
}
export interface SupervisorDashboard { caseload: SupervisorCaseloadItem[] }

export const useSupervisorDashboard = () =>
  useQuery({ queryKey: ['dashboard', 'supervisor'], queryFn: () => api.get<SupervisorDashboard>('/dashboards/supervisor') })
