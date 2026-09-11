export interface BriefChange {
  kind: 'milestone' | 'funding' | 'meeting' | 'flag' | string
  label: string
  detail?: string | null
}

export interface BriefProvenance {
  source: 'model' | 'fallback'
  model?: string | null
  latency_ms?: number | null
  reason?: string | null
}

export interface MeetingBriefPayload {
  student: { id: string; name: string; ref: string }
  lastMeetingOn: string | null
  lastMeetingActions: string | null
  daysSinceLast: number | null
  nextMeetingOn: string | null
  changes: BriefChange[]
  openFlags: string[]
  paragraph: string
  provenance: BriefProvenance
  suggestedQuestions: string[]
  modelLive: boolean
}
