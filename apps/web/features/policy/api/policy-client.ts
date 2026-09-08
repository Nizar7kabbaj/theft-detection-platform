import {
  type PolicyPayload,
  type PolicyResponse,
  policyResponseSchema,
} from "@/features/policy/schemas/policy"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export function savePolicy(
  expectedVersion: number,
  policy: PolicyPayload,
): Promise<PolicyResponse> {
  return apiRequest("/api/v1/policy/detection", {
    method: "PUT",
    body: { expected_version: expectedVersion, policy },
    schema: policyResponseSchema,
  })
}
