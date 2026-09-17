/**
 * Plain-English explainers for the statutory jargon that peppers /statutory. Each entry is one
 * sentence — enough to unblock a Registry admin who's seeing HUSID / STULOAD for the first time,
 * short enough to fit in a tooltip. Static (no runtime LLM call) — deterministic and cached at
 * build time. When you add a term here, sprinkle a <JargonTip term="…" /> next to it in the UI.
 */
export const JARGON: Record<string, string> = {
  // HESA-specific codes
  HUSID: 'HESA Unique Student Identifier — a 13-digit code (institution code + entry year + sequence + Luhn check) that HESA uses to identify each student across returns.',
  STULOAD: 'Study load — the student\'s enrolment intensity as a percentage. 100 = full time, 50 = half time. Averaged across the academic year for the return.',
  SEXID: 'HESA code for the student\'s sex identifier (allowed values include a "prefer not to say" code).',
  ETHNIC: 'HESA code for the student\'s ethnicity, from the coding frame published in the spec.',
  DISABLE: 'HESA code for declared disability, from the published coding frame; "00" is the standard code for "no known disability".',
  NATION: 'HESA code for the student\'s nationality.',
  DOMICILE: 'HESA code for the student\'s permanent home domicile before starting the course.',
  BIRTHDTE: 'Student\'s date of birth in YYYYMMDD format (HESA requirement).',
  COMDATE: 'Commencement date — when the student started the current spell of study, in YYYYMMDD format.',
  ENDDATE: 'Expected end date of the current spell of study, in YYYYMMDD format.',
  COURSEID: 'Provider\'s own code for the course the student is on.',
  MSTUFEE: 'HESA code for the fee status of the student (Home / Overseas / etc.).',
  FEESTAT: 'HESA-published code frame for major fee status categories.',
  MODE: 'Mode of study — Full-Time / Part-Time / etc., in the HESA coding frame.',
  ENTRYROUTE: 'How the student entered the programme — through the recruitment funnel or direct enrolment.',

  // Platform concepts
  'keyed on record':
    'Where on the student record the platform actually reads this value from (e.g. "Person > date of birth"). If it says "not yet captured", the platform has no source column for this field and you need to set a default.',
  'coding frame':
    'The list of values HESA accepts for a coded field. If the produced value isn\'t in the frame, validation rejects it.',
  'allowed values':
    'The HESA-published coding frame for this field. The dropdown offers only these; anything outside is rejected by validation.',
  transform:
    'How the raw record value is normalised on the way out — e.g. `upper` uppercases, `date_compact` renders YYYYMMDD. Multiple can be chained with `|` (applied left to right).',
  'default when empty':
    'The value the return will send if the record\'s source column resolves to empty. Set here once and applied to every student the return covers — no per-record edit needed.',
  'source expression':
    'The dotted path the platform reads on each student record (e.g. `student.startDate`). "unmapped" means no source is set — the field will always be empty unless a default is provided.',
  suppress:
    'Turn off a validation rule for this profile (or the whole spec pack). Only defensible when the rule itself is wrong — hides errors without fixing them, so a reason is required and it\'s visible on the sign-off card.',
  'spec pack':
    'The HESA specification the return is validated against — the field list + coding frames + cross-field rules. Versioned per academic year; a new version arrives via an accepted advisory.',
  'sign off':
    'Attest that the mappings are complete for the return. A signed-off profile is locked (edits refused) until it\'s unsigned, so the return that was submitted can always be reproduced.',
  'mandatory field':
    'A field the HESA spec requires to be present in the return. Every mandatory field must be mapped (or defaulted) before the profile can be signed off.',
  'validation report':
    'One row per problem the return would ship with today — grouped by field. Errors block sign-off; warnings don\'t.',
  'return': 'The statutory data file the platform builds and hands to HESA (one profile → one file per academic year).',
}

/** Case-insensitive lookup; also handles the common variations (SEX ID → SEXID). */
export function jargonFor(term: string): string | null {
  const key = term.trim()
  if (JARGON[key]) return JARGON[key]
  const upper = key.toUpperCase()
  if (JARGON[upper]) return JARGON[upper]
  const lower = key.toLowerCase()
  return JARGON[lower] ?? null
}
