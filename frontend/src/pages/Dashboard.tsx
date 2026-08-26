import { useEffect, useState } from "react"
import { getHealth, getInsights } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Dashboard() {
  const [health, setHealth] = useState<string | null>(null)
  const [insights, setInsights] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((res) => setHealth(res.status))
      .catch((err) => setError(String(err)))

    getInsights()
      .then((res) => setInsights(res))
      .catch((err) => setError(String(err)))
  }, [])

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-3xl font-bold">Dashboard</h1>
      <Card>
        <CardHeader>
          <CardTitle>Backend Connection Test</CardTitle>
          <CardDescription>Live check against your FastAPI backend</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {error && <p className="text-red-600">Error: {error}</p>}
          <p>Health status: <span className="font-mono">{health ?? "loading..."}</span></p>
          <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto max-h-64">
            {insights ? JSON.stringify(insights, null, 2) : "loading insights..."}
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}