import * as z from "zod/mini"

export const telegramStatusSchema = z.object({
  linked: z.boolean(),
  linked_at: z.nullable(z.string()),
})
export type TelegramStatus = z.output<typeof telegramStatusSchema>

export const telegramLinkSchema = z.object({
  url: z.string().check(z.startsWith("https://t.me/"), z.maxLength(200)),
  expires_at: z.string(),
})
export type TelegramLink = z.output<typeof telegramLinkSchema>
