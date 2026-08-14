import {
  getReachability,
  getServerReachability,
  probe,
  type Reachability,
  subscribeReachability,
} from "@/lib/network/connectivity"
import "client-only"
import { useSyncExternalStore } from "react"

export function useReachability(): Reachability {
  return useSyncExternalStore(subscribeReachability, getReachability, getServerReachability)
}

export function useIsOffline(): boolean {
  return useReachability() === "offline"
}

export function recheckReachability(): Promise<Reachability> {
  return probe()
}
