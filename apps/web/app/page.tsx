import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DetectionChart } from "@/features/analytics/components/detection-chart"

export default function Home() {
  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col gap-6 p-8">
      <Card>
        <CardHeader>
          <CardTitle>detections per hour</CardTitle>
          <CardDescription>static sample, no api calls in this scope</CardDescription>
        </CardHeader>
        <CardContent>
          <DetectionChart />
        </CardContent>
      </Card>
    </main>
  )
}
