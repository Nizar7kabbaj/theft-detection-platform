import * as z from "zod/mini"

export const concealmentPolicySchema = z.object({
  grab_ratio: z.number().check(z.gte(0.1), z.lte(1.5)),
  missing_seconds: z.number().check(z.gte(0.2), z.lte(5)),
  keypoint_confidence: z.number().check(z.gte(0.1), z.lte(0.95)),
  expiry_seconds: z.number().check(z.gte(2), z.lte(60)),
})

export const classifierPolicySchema = z.object({
  anomaly_threshold: z.number().check(z.gte(0.05), z.lte(0.95)),
  person_confidence: z.number().check(z.gte(0.1), z.lte(0.95)),
  object_confidence: z.number().check(z.gte(0.05), z.lte(0.95)),
})

export const policyPayloadSchema = z.object({
  concealment: concealmentPolicySchema,
  classifier: classifierPolicySchema,
})

export type PolicyPayload = z.output<typeof policyPayloadSchema>

export const policyRuntimeSchema = z.object({
  version: z.nullish(z.number()),
  applied_at: z.nullish(z.iso.datetime({ offset: true })),
  device: z.nullish(z.string().check(z.maxLength(32))),
})

export type PolicyRuntime = z.output<typeof policyRuntimeSchema>

export const policyResponseSchema = z.object({
  version: z.number(),
  policy: policyPayloadSchema,
  changed_by: z.string().check(z.maxLength(64)),
  changed_at: z.iso.datetime({ offset: true }),
  runtime: policyRuntimeSchema,
})

export type PolicyResponse = z.output<typeof policyResponseSchema>

export const policyChangeSchema = z.object({
  field_name: z.string().check(z.maxLength(64)),
  previous: z.number(),
  current: z.number(),
})

export type PolicyChange = z.output<typeof policyChangeSchema>

export const policyRevisionSchema = z.object({
  version: z.number(),
  changed_by: z.string().check(z.maxLength(64)),
  changed_at: z.iso.datetime({ offset: true }),
  changes: z.array(policyChangeSchema),
})

export type PolicyRevision = z.output<typeof policyRevisionSchema>

export const policyHistorySchema = z.array(policyRevisionSchema)

import type { LucideIcon } from "lucide-react"
import { BellOff, Eye, Hand, Package, ScanFace, Timer, UserRound } from "lucide-react"

type PolicyFieldBase = {
  path: string
  label: string
  hint: string
  icon: LucideIcon
  unit: "seconds" | "percent" | "ratio"
  min: number
  max: number
  step: number
}

export type PolicyField =
  | (PolicyFieldBase & { group: "concealment"; key: keyof PolicyPayload["concealment"] })
  | (PolicyFieldBase & { group: "classifier"; key: keyof PolicyPayload["classifier"] })

export function readField(policy: PolicyPayload, field: PolicyField): number {
  return field.group === "concealment"
    ? policy.concealment[field.key]
    : policy.classifier[field.key]
}

export function writeField(
  policy: PolicyPayload,
  field: PolicyField,
  value: number,
): PolicyPayload {
  return field.group === "concealment"
    ? { ...policy, concealment: { ...policy.concealment, [field.key]: value } }
    : { ...policy, classifier: { ...policy.classifier, [field.key]: value } }
}

export const CONCEALMENT_FIELDS: readonly PolicyField[] = [
  {
    path: "concealment.grab_ratio",
    group: "concealment",
    key: "grab_ratio",
    label: "how close a hand must be",
    hint: "an item further from the hand than this is not treated as picked up",
    icon: Hand,
    unit: "ratio",
    min: 0.1,
    max: 1.5,
    step: 0.05,
  },
  {
    path: "concealment.missing_seconds",
    group: "concealment",
    key: "missing_seconds",
    label: "how long before an item counts as gone",
    hint: "shorter reacts faster, longer ignores items the camera briefly loses",
    icon: Timer,
    unit: "seconds",
    min: 0.2,
    max: 5,
    step: 0.1,
  },
  {
    path: "concealment.keypoint_confidence",
    group: "concealment",
    key: "keypoint_confidence",
    label: "how clearly the person must be seen",
    hint: "raise it in a crowded aisle to stop guessing from a half-hidden body",
    icon: ScanFace,
    unit: "percent",
    min: 0.1,
    max: 0.95,
    step: 0.05,
  },
  {
    path: "concealment.expiry_seconds",
    group: "concealment",
    key: "expiry_seconds",
    label: "quiet time after an alert",
    hint: "one camera stays silent this long before it can alert again",
    icon: BellOff,
    unit: "seconds",
    min: 2,
    max: 60,
    step: 1,
  },
]

export const CLASSIFIER_FIELDS: readonly PolicyField[] = [
  {
    path: "classifier.anomaly_threshold",
    group: "classifier",
    key: "anomaly_threshold",
    label: "how suspicious movement must look",
    hint: "lower catches more and alerts more often, higher only flags the obvious",
    icon: Eye,
    unit: "percent",
    min: 0.05,
    max: 0.95,
    step: 0.05,
  },
  {
    path: "classifier.person_confidence",
    group: "classifier",
    key: "person_confidence",
    label: "how sure before following a person",
    hint: "lower follows people further from the camera and mistakes more shapes for people",
    icon: UserRound,
    unit: "percent",
    min: 0.1,
    max: 0.95,
    step: 0.05,
  },
  {
    path: "classifier.object_confidence",
    group: "classifier",
    key: "object_confidence",
    label: "how sure before watching an item",
    hint: "lower watches items on a busy shelf and mistakes more shapes for stock",
    icon: Package,
    unit: "percent",
    min: 0.05,
    max: 0.95,
    step: 0.05,
  },
]

export const DEFAULT_POLICY: PolicyPayload = {
  concealment: {
    grab_ratio: 0.6,
    missing_seconds: 1,
    keypoint_confidence: 0.5,
    expiry_seconds: 10,
  },
  classifier: {
    anomaly_threshold: 0.6,
    person_confidence: 0.7,
    object_confidence: 0.35,
  },
}

export function isDefault(policy: PolicyPayload): boolean {
  return [...CONCEALMENT_FIELDS, ...CLASSIFIER_FIELDS].every(
    (field) => readField(policy, field) === readField(DEFAULT_POLICY, field),
  )
}

export const FIELD_LABELS = new Map<string, string>(
  [...CONCEALMENT_FIELDS, ...CLASSIFIER_FIELDS].map((field) => [field.path, field.label]),
)

export const FIELD_UNITS = new Map<string, PolicyField["unit"]>(
  [...CONCEALMENT_FIELDS, ...CLASSIFIER_FIELDS].map((field) => [field.path, field.unit]),
)
