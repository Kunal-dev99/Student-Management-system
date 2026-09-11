export interface QueuePick {
  id: string
  reasoning: string
}

export interface QueueRow {
  student_id: string
  student_ref: string
  person_name: string
  score: number
  reasons: string[]
}

export interface QueueProvenance {
  source: 'model' | 'fallback'
  model?: string | null
  latency_ms?: number | null
  reason?: string | null
}

export interface WeeklyQueuePayload {
  picks: QueuePick[]
  provenance: QueueProvenance
  candidates: QueueRow[]
  modelLive: boolean
}
