export const POLICY_SECTION_COOKIE_NAME = "policy_section"
export const POLICY_SECTION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

export const SECTION_IDS = ["concealment", "classifier", "history"] as const

export type SectionId = (typeof SECTION_IDS)[number]

export const DEFAULT_SECTION: SectionId = "concealment"

export function parseStoredSection(value: string | undefined | null): SectionId {
  if (value === undefined || value === null) {
    return DEFAULT_SECTION
  }
  const match = SECTION_IDS.find((candidate) => candidate === value)
  return match ?? DEFAULT_SECTION
}
