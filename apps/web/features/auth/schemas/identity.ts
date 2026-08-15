import { z } from "zod"
import type { components } from "@/types/api"

type IdentityResponse = components["schemas"]["IdentityResponse"]

export type Permission = components["schemas"]["Permission"]

export const identityResponseSchema = z.object({
  user_id: z.string().max(64),
  username: z.string().max(50),
  roles: z.array(z.string().max(32)).max(16),
  permissions: z.array(z.string().max(64)).max(64),
})

export type Identity = z.output<typeof identityResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type FieldsOnlyInContract = Exclude<keyof IdentityResponse, keyof Identity>
type FieldsOnlyInSchema = Exclude<keyof Identity, keyof IdentityResponse>
type FieldsWithChangedType = {
  [K in keyof Concrete<IdentityResponse>]: K extends keyof Concrete<Identity>
    ? Concrete<IdentityResponse>[K] extends Concrete<Identity>[K]
      ? never
      : K
    : never
}[keyof Concrete<IdentityResponse>]
type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]
