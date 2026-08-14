import { z } from "zod"

export const loginSchema = z.object({
  username: z.string().trim().min(1, "username is required").max(50, "username is too long"),
  password: z.string().min(1, "password is required"),
})

export type LoginInput = z.infer<typeof loginSchema>

export const tokenResponseSchema = z.object({
  token_type: z.string(),
  expires_in: z.number().int().positive(),
})
