"use client"

import { ChevronLeft, ChevronRight, UserPlus } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  type StatusFilter,
  serializeFilters,
  USER_FILTERS_COOKIE_MAX_AGE,
  USER_FILTERS_COOKIE_NAME,
  type UserFilters,
} from "@/features/users/api/user-cookie"
import { AccessPanel } from "@/features/users/components/access-panel"
import { CreateUserDialog } from "@/features/users/components/create-user-dialog"
import { UserActions } from "@/features/users/components/user-actions"
import { RoleChips, StatusChip } from "@/features/users/components/user-chips"
import { initials, relativeTime, shortDate } from "@/features/users/lib/format"
import {
  ROLE_LABELS,
  ROLE_VALUES,
  type RolePermissionMap,
  type UserSummary,
} from "@/features/users/schemas/user"
import { writeCookie } from "@/lib/cookies/write"
import { cn } from "@/lib/utils"

const HEAD_CELL = "px-3 pb-2 pt-2 text-left font-normal"
const BODY_CELL = "px-3 py-2.5"
const SEARCH_DELAY_MS = 350

function firstId(users: readonly UserSummary[], stored: string): string | null {
  if (stored !== "" && users.some((user) => user.id === stored)) {
    return stored
  }
  return users[0]?.id ?? null
}

export function UserConsole({
  initialUsers,
  total,
  pageSize,
  permissionMap,
  renderedAt,
  canWrite,
  currentUserId,
  initialFilters,
}: {
  initialUsers: readonly UserSummary[]
  total: number
  pageSize: number
  permissionMap: RolePermissionMap
  renderedAt: number
  canWrite: boolean
  currentUserId: string
  initialFilters: UserFilters
}) {
  const router = useRouter()
  const [users, setUsers] = useState<readonly UserSummary[]>(initialUsers)
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState(initialFilters.search)
  const [role, setRole] = useState(initialFilters.role)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(initialFilters.status)
  const [page, setPage] = useState(initialFilters.page)
  const [accessOpen, setAccessOpen] = useState(initialFilters.access)
  const [selectedId, setSelectedId] = useState<string | null>(
    firstId(initialUsers, initialFilters.selected),
  )
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setUsers(initialUsers)
    setSelectedId((current) =>
      current !== null && initialUsers.some((user) => user.id === current)
        ? current
        : (initialUsers[0]?.id ?? null),
    )
  }, [initialUsers])

  useEffect(() => {
    return () => {
      if (timer.current !== null) {
        clearTimeout(timer.current)
      }
    }
  }, [])

  function persist(next: Partial<UserFilters>, refresh: boolean) {
    const merged: UserFilters = {
      search,
      role,
      status: statusFilter,
      selected: selectedId ?? "",
      page,
      access: accessOpen,
      ...next,
    }
    writeCookie(USER_FILTERS_COOKIE_NAME, serializeFilters(merged), USER_FILTERS_COOKIE_MAX_AGE)
    if (refresh) {
      router.refresh()
    }
  }

  function onSearch(value: string) {
    setSearch(value)
    setPage(0)
    if (timer.current !== null) {
      clearTimeout(timer.current)
    }
    timer.current = setTimeout(() => {
      persist({ search: value, page: 0 }, true)
    }, SEARCH_DELAY_MS)
  }

  function select(userId: string) {
    setSelectedId(userId)
    persist({ selected: userId }, true)
  }

  function goToPage(next: number) {
    setPage(next)
    persist({ page: next }, true)
  }

  const selected = useMemo(
    () => users.find((user) => user.id === selectedId) ?? null,
    [users, selectedId],
  )

  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1)
  const from = total === 0 ? 0 : page * pageSize + 1
  const to = Math.min(total, page * pageSize + users.length)

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground uppercase tracking-widest">
              account directory
            </span>
            <span className="text-foreground text-lg">who can access the platform</span>
            <span className="text-muted-foreground text-xs">
              roles decide access, sessions end when an account is disabled
            </span>
          </div>
          {canWrite ? (
            <Button variant="default" size="sm" onClick={() => setCreating(true)}>
              <UserPlus data-icon="inline-start" />
              create user
            </Button>
          ) : null}
        </div>
      </Card>

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              placeholder="search username"
              className="h-8 flex-1 rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring"
            />
            <select
              value={role}
              onChange={(event) => {
                setRole(event.target.value)
                setPage(0)
                persist({ role: event.target.value, page: 0 }, true)
              }}
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm outline-none focus-visible:border-ring"
            >
              <option value="">all roles</option>
              {ROLE_VALUES.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS.get(value)}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => {
                const next = event.target.value as StatusFilter
                setStatusFilter(next)
                setPage(0)
                persist({ status: next, page: 0 }, true)
              }}
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm outline-none focus-visible:border-ring"
            >
              <option value="all">all status</option>
              <option value="active">active</option>
              <option value="disabled">disabled</option>
            </select>
          </div>

          {users.length === 0 ? (
            <div className="rounded-lg border border-border border-dashed py-10 text-center text-muted-foreground text-sm">
              no account matches this filter
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-muted/40">
                  <tr className="text-[10px] text-muted-foreground uppercase tracking-widest">
                    <th className={HEAD_CELL}>user</th>
                    <th className={HEAD_CELL}>roles</th>
                    <th className={HEAD_CELL}>status</th>
                    <th className={HEAD_CELL}>last active</th>
                    <th className={HEAD_CELL}>created</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      onClick={() => select(user.id)}
                      className={cn(
                        "cursor-pointer border-border/60 border-t transition-colors hover:bg-muted/40",
                        user.id === selectedId ? "bg-muted/60" : null,
                      )}
                    >
                      <td className={BODY_CELL}>
                        <span className="flex items-center gap-2">
                          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-[10px] text-muted-foreground">
                            {initials(user.username)}
                          </span>
                          <span className="text-foreground">{user.username}</span>
                        </span>
                      </td>
                      <td className={BODY_CELL}>
                        <RoleChips roles={user.roles} />
                      </td>
                      <td className={BODY_CELL}>
                        <StatusChip isActive={user.is_active} />
                      </td>
                      <td className={cn(BODY_CELL, "font-mono text-muted-foreground text-xs")}>
                        {relativeTime(user.last_active_at, renderedAt)}
                      </td>
                      <td className={cn(BODY_CELL, "font-mono text-muted-foreground text-xs")}>
                        {shortDate(user.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-muted-foreground text-xs tabular-nums">
              {from} to {to} of {total}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => goToPage(page - 1)}
                disabled={page === 0}
                aria-label="previous page"
              >
                <ChevronLeft />
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => goToPage(page + 1)}
                disabled={page >= lastPage}
                aria-label="next page"
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
        </Card>

        <Card className="flex flex-col gap-4 p-4">
          {selected === null ? (
            <p className="text-muted-foreground text-sm">select an account to see its access</p>
          ) : (
            <>
              <div className="flex flex-col items-start gap-2">
                <span className="text-[11px] text-muted-foreground uppercase tracking-widest">
                  selected user
                </span>
                <span className="flex size-12 items-center justify-center rounded-full bg-muted font-mono text-muted-foreground text-sm">
                  {initials(selected.username)}
                </span>
                <span className="text-foreground text-lg">{selected.username}</span>
                <RoleChips roles={selected.roles} />
                <StatusChip isActive={selected.is_active} />
              </div>
              <div className="grid grid-cols-2 gap-3 border-border/50 border-t pt-3">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
                    created
                  </span>
                  <span className="font-mono text-foreground text-xs">
                    {shortDate(selected.created_at)}
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
                    last active
                  </span>
                  <span className="font-mono text-foreground text-xs">
                    {relativeTime(selected.last_active_at, renderedAt)}
                  </span>
                </div>
              </div>
              <div className="border-border/50 border-t pt-3">
                <AccessPanel
                  map={permissionMap}
                  roles={selected.roles}
                  open={accessOpen}
                  onOpenChange={(next) => {
                    setAccessOpen(next)
                    persist({ access: next }, true)
                  }}
                />
              </div>
              {canWrite ? (
                <div className="border-border/50 border-t pt-3">
                  <UserActions
                    key={selected.id}
                    user={selected}
                    isSelf={selected.id === currentUserId}
                    onUpdated={(updated) => {
                      setUsers((current) =>
                        current.map((entry) => (entry.id === updated.id ? updated : entry)),
                      )
                      router.refresh()
                    }}
                    onDeleted={(removedId) => {
                      setUsers((current) => current.filter((entry) => entry.id !== removedId))
                      router.refresh()
                    }}
                  />
                </div>
              ) : null}
            </>
          )}
        </Card>
      </div>

      <CreateUserDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(user) => {
          select(user.id)
          router.refresh()
        }}
      />
    </div>
  )
}
