'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface IcrPathwaySummary {
  code: string
  label: string
  detail: string
  durationMonths: number
  clinical: boolean
  students: number
  upgraded: number
  provisional: number
}

export interface IcrFunder {
  name: string
  funderType: string | null
  students: number
  committedStipend: string | null
}

export interface IcrOverview {
  cohort: number
  allTime: number
  pathways: IcrPathwaySummary[]
  transferViva: { awaiting: number; dueSoon: number; overdue: number; upgraded: number }
  nearSubmissionLimit: number
  funders: IcrFunder[]
}

export interface TransferVivaRow {
  studentId: string
  studentRef: string
  name: string
  startDate: string | null
  monthsIn: number | null
  dueDate: string | null
  daysUntilDue: number | null
  milestoneStatus: string
  registration: string
  state: 'overdue' | 'due soon' | 'scheduled' | 'upgraded'
  requiredDocuments: Record<string, string> | null
  panel: Record<string, string[]> | null
}

export interface PathwayRow {
  studentId: string
  studentRef: string
  name: string
  pathway: string
  clinical: boolean
  status: string
  studyMode: string
  startDate: string | null
  monthsIn: number | null
  limitMonths: number
  monthsRemaining: number | null
  registration: string
  checkpointsPassed: number
  checkpointsTotal: number
  dataBarrier: string | null
}

export const useIcrOverview = () =>
  useQuery({ queryKey: ['icr', 'overview'], queryFn: () => api.get<IcrOverview>('/icr/overview') })

export const useTransferViva = () =>
  useQuery({
    queryKey: ['icr', 'transfer-viva'],
    queryFn: () => api.get<{ rows: TransferVivaRow[]; checkpoint: string }>('/icr/transfer-viva'),
  })

export const useIcrPathways = () =>
  useQuery({ queryKey: ['icr', 'pathways'], queryFn: () => api.get<{ rows: PathwayRow[] }>('/icr/pathways') })

export const useIcrFunding = () =>
  useQuery({
    queryKey: ['icr', 'funding'],
    queryFn: () => api.get<{ funders: IcrFunder[]; totalStudents: number }>('/icr/funding'),
  })
