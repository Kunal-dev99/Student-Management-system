/**
 * PGR Intelligence — shared interaction grammar.
 *
 * Import from `@/features/intelligence` so every consumer picks up the exact same
 * components. The four verbs (Explain / Evidence / Simulate / Prepare action) map to
 * IntelligenceStrip's buttons; the four drawers are reusable on every screen.
 */
export { AIStateBanner } from './AIStateBanner'
export type { AIStateBannerProps } from './AIStateBanner'

export { SourceChip } from './SourceChip'
export type { SourceChipProps } from './SourceChip'

export { NarratedParagraph } from './NarratedParagraph'
export type { NarratedParagraphProps, Narration } from './NarratedParagraph'

export { LiveDot } from './LiveDot'
export { useTypewriter, TypingCursor } from './useTypewriter'

export { EvidenceDrawer } from './EvidenceDrawer'
export type { EvidenceDrawerProps } from './EvidenceDrawer'

export { ScenarioDrawer } from './ScenarioDrawer'
export type { ScenarioDrawerProps } from './ScenarioDrawer'

export { ActionPlanDrawer } from './ActionPlanDrawer'
export type { ActionPlanDrawerProps } from './ActionPlanDrawer'

export { IntelligenceStrip } from './IntelligenceStrip'
export type { IntelligenceStripProps } from './IntelligenceStrip'

export { TrajectoryChart } from './TrajectoryChart'
export type { TrajectoryChartProps, TrajectoryPoint } from './TrajectoryChart'

export { EngagementPanel } from './EngagementPanel'
export type { EngagementPanelProps } from './EngagementPanel'

export { CaseContextRail } from './CaseContextRail'
export type { CaseContextRailProps } from './CaseContextRail'

export { WeeklyInterventionQueue } from './WeeklyInterventionQueue'

export { TwinTimeline } from './TwinTimeline'
export type { TwinTimelineProps, TimelineEvent } from './TwinTimeline'

export { RiskStoryline } from './RiskStoryline'
export type { RiskStorylineProps } from './RiskStoryline'

export { InsightsPanel } from './InsightsPanel'
export type { InsightsPanelProps } from './InsightsPanel'

export { CaseExplorer } from './CaseExplorer'
export { PolicyCompilerWorkspace } from './PolicyCompilerWorkspace'
export { CommitmentReviewDrawer } from './CommitmentReviewDrawer'
export type { CommitmentReviewDrawerProps } from './CommitmentReviewDrawer'

export { ChangeRadarWorkspace } from './ChangeRadarWorkspace'

export * from './api'
