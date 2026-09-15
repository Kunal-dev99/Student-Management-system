/**
 * Student-360 panel visibility — the "park" config (ICR).
 *
 * The student record grew a lot of panels; ICR only needs the operational core. Rather than
 * delete the extras, we PARK them: the components stay imported and in the tree, but they don't
 * render while their flag is `false`. Flip a flag back to `true` to restore a panel instantly —
 * nothing else changes. Parked panels are mostly the AI/intelligence extras and secondary views.
 *
 * (A future step can source these from an institution setting; for now it's a single edit point.)
 */
export const STUDENT_PANELS = {
  // --- Core operational record (kept) ---
  journeyTracker: true,
  record: true,
  lifecycle: true,          // suspensions/extensions/mode + study intensity (G4)
  supervisors: true,
  supervisionMeetings: true,
  milestones: true,         // progression milestones (G3)
  funding: true,
  taughtOrThesis: true,     // taught (G1) vs research thesis/classification
  documents: true,
  history: true,
  person: true,

  // --- Parked (AI/intelligence extras + secondary views) ---
  meetingBrief: false,      // "Prepare for meeting" AI drawer
  intelligenceStrip: false, // PGR Intelligence strip
  insights: false,          // AI Case Insights (streaming)
  twinTimeline: false,      // Digital Twin timeline
  riskStoryline: false,     // Pattern Lab risk storyline
  engagement: false,        // Engagement panel
  fundingLineage: false,    // funding lineage panel
  supervisorRequests: false,// supervisor-assignment requests card
  relationshipGraph: false, // folded relationship map
} as const

export type StudentPanelKey = keyof typeof STUDENT_PANELS
