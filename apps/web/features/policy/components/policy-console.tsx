"use client"

import { ChevronRight, Eye, Hand, History, type LucideIcon, RotateCcw } from "lucide-react"
import { useRouter } from "next/navigation"
import { type ReactNode, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { savePolicy } from "@/features/policy/api/policy-client"
import { PolicySlider } from "@/features/policy/components/policy-slider"
import {
  CLASSIFIER_FIELDS,
  CONCEALMENT_FIELDS,
  DEFAULT_POLICY,
  isDefault,
  type PolicyField,
  type PolicyPayload,
  readField,
  writeField,
} from "@/features/policy/schemas/policy"
import { ApiError } from "@/lib/api/errors"
import { cn } from "@/lib/utils"

type SectionId = "concealment" | "classifier" | "history"

const SECTIONS: readonly { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: "concealment", label: "taking an item", icon: Hand },
  { id: "classifier", label: "suspicious movement", icon: Eye },
  { id: "history", label: "what changed", icon: History },
]

function countChanges(draft: PolicyPayload, saved: PolicyPayload): number {
  return [...CONCEALMENT_FIELDS, ...CLASSIFIER_FIELDS].filter(
    (field) => readField(draft, field) !== readField(saved, field),
  ).length
}

function saveFailure(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return "the policy changed while this page was open, reload to see the current values"
  }
  if (error instanceof ApiError && error.status === 422) {
    return "a value fell outside the allowed range and was rejected"
  }
  return "the change was not saved, the detector is still on the previous policy"
}

export function PolicyConsole({
  version,
  saved,
  canWrite,
  history,
}: {
  version: number
  saved: PolicyPayload
  canWrite: boolean
  history: ReactNode
}) {
  const router = useRouter()
  const [draft, setDraft] = useState<PolicyPayload>(saved)
  const [section, setSection] = useState<SectionId>("concealment")
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const pending = countChanges(draft, saved)

  function change(field: PolicyField, value: number) {
    setFailure(null)
    setDraft((current) => writeField(current, field, value))
  }

  async function save() {
    setSaving(true)
    setFailure(null)
    try {
      await savePolicy(version, draft)
      router.refresh()
    } catch (error) {
      setFailure(saveFailure(error))
    } finally {
      setSaving(false)
    }
  }

  function panel(eyebrow: string, title: string, fields: readonly PolicyField[]) {
    return (
      <Card className="flex flex-col gap-1 p-4">
        <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
          {eyebrow}
        </span>
        <span className="mb-2 text-foreground text-lg">{title}</span>
        {fields.map((field) => (
          <PolicySlider
            key={field.path}
            field={field}
            value={readField(draft, field)}
            saved={readField(saved, field)}
            canWrite={canWrite}
            onChange={(value) => change(field, value)}
          />
        ))}
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
      <Card className="flex flex-col gap-1 p-2">
        <span className="px-2 py-1.5 text-[10px] text-muted-foreground uppercase tracking-widest">
          configuration
        </span>
        {SECTIONS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setSection(entry.id)}
            className={cn(
              "flex min-h-10 items-center gap-2.5 rounded-sm px-2.5 text-left text-sm outline-none transition-[background-color,color,scale] duration-150 focus-visible:ring-3 focus-visible:ring-ring/50 active:scale-[0.96]",
              section === entry.id
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            <entry.icon className="size-4 shrink-0" />
            <span className="flex-1">{entry.label}</span>
            <ChevronRight className="size-3.5 shrink-0 opacity-60" />
          </button>
        ))}
        <span className="border-border/50 border-t px-2.5 pt-2.5 pb-1 text-[11px] text-muted-foreground">
          {canWrite ? "changes reach the detector on save" : "read only, changing needs admin"}
        </span>
      </Card>

      <div className="flex flex-col gap-4">
        {section === "concealment"
          ? panel(
              "taking an item",
              "when an item leaves the shelf and does not come back",
              CONCEALMENT_FIELDS,
            )
          : null}
        {section === "classifier"
          ? panel(
              "suspicious movement",
              "when how someone moves looks like theft",
              CLASSIFIER_FIELDS,
            )
          : null}
        {section === "history" ? history : null}
        {canWrite && section !== "history" ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-muted-foreground text-xs">
              {failure ?? (pending === 0 ? "no unsaved change" : `${pending} unsaved`)}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setDraft(DEFAULT_POLICY)
                  setFailure(null)
                }}
                disabled={saving || isDefault(draft)}
              >
                <RotateCcw data-icon="inline-start" />
                back to defaults
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(saved)
                  setFailure(null)
                }}
                disabled={pending === 0 || saving}
              >
                discard
              </Button>
              <Button variant="default" size="sm" onClick={save} disabled={pending === 0 || saving}>
                {saving ? "saving" : "save and push to edge"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
