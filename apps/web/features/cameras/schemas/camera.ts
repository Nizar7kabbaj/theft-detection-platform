import * as z from "zod/mini"
import type { components } from "@/types/api"

type CameraContract = components["schemas"]["CameraResponse"]
type HealthViewContract = components["schemas"]["CameraHealthView"]

export const HEALTH_STATE_VALUES = ["online", "degraded", "offline", "unknown"] as const

const healthState = z.enum(HEALTH_STATE_VALUES)

export type HealthState = z.output<typeof healthState>

export const healthViewSchema = z.object({
  state: healthState,
  last_frame_at: z.nullish(z.iso.datetime({ offset: true })),
  age_seconds: z.nullish(z.number()),
})

export type HealthView = z.output<typeof healthViewSchema>

export const cameraSchema = z.object({
  _id: z.string().check(z.minLength(1), z.maxLength(128)),
  camera_id: z.string().check(z.minLength(1), z.maxLength(128)),
  name: z.string().check(z.minLength(1), z.maxLength(256)),
  location: z.string().check(z.maxLength(256)),
  stream_url: z.nullish(z.string().check(z.maxLength(2048))),
  status: z.string().check(z.maxLength(64)),
  health: z.optional(healthViewSchema),
  created_at: z.iso.datetime({ offset: true }),
})

export type Camera = z.output<typeof cameraSchema>

export const cameraListSchema = z.array(cameraSchema)

const UNKNOWN_HEALTH: HealthView = {
  state: "unknown",
  last_frame_at: null,
  age_seconds: null,
}

export function cameraHealth(camera: Camera): HealthView {
  return camera.health ?? UNKNOWN_HEALTH
}

export const healthEventSchema = z.object({
  camera_id: z.string().check(z.minLength(1), z.maxLength(128)),
  state: healthState,
  last_frame_at: z.nullish(z.number()),
  age_seconds: z.nullish(z.number()),
})

export type HealthEvent = z.output<typeof healthEventSchema>

export function healthEventToView(event: HealthEvent): HealthView {
  const lastFrameAt =
    event.last_frame_at === null || event.last_frame_at === undefined
      ? null
      : new Date(event.last_frame_at * 1000).toISOString()
  return {
    state: event.state,
    last_frame_at: lastFrameAt,
    age_seconds: event.age_seconds ?? null,
  }
}

type Concrete<T> = { [K in keyof T]-?: T[K] }

type FieldsOnlyInContract = Exclude<keyof CameraContract, keyof Camera>
type FieldsOnlyInSchema = Exclude<keyof Camera, keyof CameraContract>
type FieldsWithChangedType = {
  [K in keyof Concrete<CameraContract>]: K extends keyof Concrete<Camera>
    ? Concrete<CameraContract>[K] extends Concrete<Camera>[K]
      ? never
      : K
    : never
}[keyof Concrete<CameraContract>]

type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>

export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]

type HealthFieldsOnlyInContract = Exclude<keyof HealthViewContract, keyof HealthView>
type HealthFieldsOnlyInSchema = Exclude<keyof HealthView, keyof HealthViewContract>
type HealthFieldsWithChangedType = {
  [K in keyof Concrete<HealthViewContract>]: K extends keyof Concrete<HealthView>
    ? Concrete<HealthViewContract>[K] extends Concrete<HealthView>[K]
      ? never
      : K
    : never
}[keyof Concrete<HealthViewContract>]

type NoHealthFieldsOnlyInContract = AssertNever<HealthFieldsOnlyInContract>
type NoHealthFieldsOnlyInSchema = AssertNever<HealthFieldsOnlyInSchema>
type NoHealthFieldsWithChangedType = AssertNever<HealthFieldsWithChangedType>

export type HealthContractDrift = [
  NoHealthFieldsOnlyInContract,
  NoHealthFieldsOnlyInSchema,
  NoHealthFieldsWithChangedType,
]
