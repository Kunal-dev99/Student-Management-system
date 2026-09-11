'use client'

import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { ComposeResponse, ComposerStatus } from './types'

export const useComposerStatus = () =>
  useQuery({
    queryKey: ['composer', 'status'],
    queryFn: () => api.get<ComposerStatus>('/composer/status'),
    // The kill switch and the API key both live outside this page; a short stale window
    // means turning the composer on in Settings takes effect without a hard reload.
    staleTime: 30_000,
  })

export function useCompose() {
  return useMutation({
    mutationFn: (question: string) =>
      api.post<ComposeResponse>('/composer', { question }),
  })
}

/** A step the composer has actually completed — never a simulated progress bar. */
export interface ProgressStep {
  kind: 'status' | 'function' | 'result' | 'composition' | 'error'
  message: string
  function?: string
  failed?: boolean
}

/**
 * Consume the SSE stream from `POST /composer/stream`.
 *
 * `EventSource` cannot POST or carry an Authorization header, so this reads the response
 * body directly. Frames are `event: <kind>\ndata: <json>\n\n`; a partial frame at the end
 * of a chunk is held back until the rest arrives.
 */
export async function streamCompose(
  question: string,
  handlers: {
    onStep: (step: ProgressStep) => void
    onDone: (result: ComposeResponse) => void
    onError: (message: string) => void
    signal?: AbortSignal
  },
): Promise<void> {
  const response = await api.raw('/composer/stream', {
    method: 'POST',
    body: JSON.stringify({ question }),
    signal: handlers.signal,
  })

  if (!response.ok || !response.body) {
    handlers.onError('The composer could not be reached.')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Keep the trailing fragment — it is the start of the next frame, not a whole one.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const eventLine = frame.split('\n').find((l) => l.startsWith('event: '))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!eventLine || !dataLine) continue

      const kind = eventLine.slice(7).trim() as ProgressStep['kind']
      let payload: Record<string, unknown>
      try {
        payload = JSON.parse(dataLine.slice(6))
      } catch {
        continue
      }

      if (kind === 'composition') {
        handlers.onDone(payload as unknown as ComposeResponse)
      } else if (kind === 'error') {
        handlers.onError(String(payload.message ?? 'Composition failed.'))
      } else {
        handlers.onStep({
          kind,
          message: String(payload.message ?? ''),
          function: payload.function as string | undefined,
          failed: payload.failed as boolean | undefined,
        })
      }
    }
  }
}

export interface ComposerRun {
  id: string
  question: string
  functionsCalled: string[]
  provider: string
  model: string
  tokensIn: number
  tokensOut: number
  latencyMs: number
  ok: boolean
  error: string | null
  createdAt: string | null
}

export const useComposerRuns = (enabled = true) =>
  useQuery({
    queryKey: ['composer', 'runs'],
    queryFn: () => api.get<ComposerRun[]>('/composer/runs?limit=25'),
    enabled,
  })
