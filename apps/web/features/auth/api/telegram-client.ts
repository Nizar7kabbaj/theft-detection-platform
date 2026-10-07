import {
  type TelegramLink,
  type TelegramStatus,
  telegramLinkSchema,
  telegramStatusSchema,
} from "@/features/auth/schemas/telegram"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export function getTelegramStatus(signal: AbortSignal): Promise<TelegramStatus> {
  return apiRequest("/auth/telegram", { signal, schema: telegramStatusSchema })
}

export function createTelegramLink(): Promise<TelegramLink> {
  return apiRequest("/auth/telegram/link", { method: "POST", schema: telegramLinkSchema })
}

export function unlinkTelegram(): Promise<void> {
  return apiRequest("/auth/telegram", { method: "DELETE" })
}
