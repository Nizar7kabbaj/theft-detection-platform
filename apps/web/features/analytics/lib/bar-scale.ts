const WIDTH: Record<number, string> = {
  0: "w-0",
  10: "w-[10%]",
  20: "w-[20%]",
  30: "w-[30%]",
  40: "w-[40%]",
  50: "w-1/2",
  60: "w-[60%]",
  70: "w-[70%]",
  80: "w-[80%]",
  90: "w-[90%]",
  100: "w-full",
}

export function barWidth(value: number, peak: number): string {
  if (peak <= 0 || value <= 0) {
    return WIDTH[0] as string
  }
  const step = Math.max(10, Math.round((value / peak) * 10) * 10)
  return (WIDTH[step] ?? WIDTH[100]) as string
}

export function share(part: number, whole: number): string {
  if (whole <= 0) {
    return "0%"
  }
  return `${Math.round((part / whole) * 100)}%`
}
