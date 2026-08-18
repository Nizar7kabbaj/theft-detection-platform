import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function AbsentPanel({ title, reason }: { title: string; reason: string }) {
  return (
    <Card className="opacity-60">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{reason}</CardDescription>
      </CardHeader>
    </Card>
  )
}
