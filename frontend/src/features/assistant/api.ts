'use client'

import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

/**
 * Ask PGR assistant (backend module `assistant`, Phase 5.1 — read-only).
 *
 * Both endpoints require the `assistant.use` permission; a caller without it gets a 403,
 * which the UI surfaces as "not available for your role" rather than an error.
 */

/**
 * Which route produced the answer:
 * - `rules`     — matched confidently on-premise (zero tokens, no data left the server)
 * - `guess`     — inferred via the concept graph; answered, but flagged so it can be corrected
 * - `model`     — the optional LLM fallback (off unless ASSISTANT_LLM_ENABLED)
 * - `unmatched` — nothing recognised; suggestions are offered instead of a guess
 */
export type AssistantPath = 'rules' | 'guess' | 'model' | 'unmatched'

export interface AssistantLink {
  label: string
  href: string
}

/** A student row emitted by the cohort/find tools — each row explains why it matched. */
export interface AssistantStudentRow {
  studentId?: string
  studentRef?: string
  personName?: string
  status?: string
  reasons?: string[]
  link?: string
}

/**
 * Free-form tool payload. The shapes we render explicitly are declared; everything else is
 * carried through untyped because it depends on which tool the assistant reached for.
 */
export interface AssistantData {
  students?: AssistantStudentRow[]
  candidates?: AssistantStudentRow[]
  count?: number
  filters?: string[]
  /** Offered when the parser didn't understand — concrete phrasings that do work. */
  didYouMean?: string[]
  llmEnabled?: boolean
  [key: string]: unknown
}

export interface AssistantAnswer {
  answer: string
  links: AssistantLink[]
  data: AssistantData
  path: AssistantPath
  /** Plain-English readback of how the question was interpreted, so it can be verified. */
  understood?: string
  toolsUsed: string[]
  /** Always true in this release — the assistant cannot mutate anything. */
  readOnly: boolean
}

/** Conversation turns replayed to the model path so follow-ups keep context. */
export interface AssistantHistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantQueryVars {
  query: string
  history?: AssistantHistoryTurn[]
}

export interface AssistantCapabilities {
  readOnly: boolean
  examples: string[]
  /** actionName -> why the assistant refuses it. */
  blockedActions: Record<string, string>
}

export const useAskAssistant = () =>
  useMutation({
    mutationFn: ({ query, history }: AssistantQueryVars) =>
      api.post<AssistantAnswer>('/assistant/query', { query, history: history ?? [] }),
  })

/**
 * Capability manifest — static per deployment, so it is cached for the session.
 * `enabled` lets a caller defer the fetch until the palette is first opened.
 */
export const useCapabilities = (enabled = true) =>
  useQuery({
    queryKey: ['assistant', 'capabilities'],
    queryFn: () => api.get<AssistantCapabilities>('/assistant/capabilities'),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    enabled,
  })
