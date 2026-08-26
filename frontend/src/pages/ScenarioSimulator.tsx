import { useEffect, useState } from "react"
import { getForecast, getChurn, type ForecastRow, type ChurnCustomerRow } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Label } from "@/components/ui/label"

function formatCurrency(value: number) {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}

export default function ScenarioSimulator() {
  const [periods, setPeriods] = useState(6)
  const [growthAdjustmentPct, setGrowthAdjustmentPct] = useState(0)
  const [forecast, setForecast] = useState<ForecastRow[] | null>(null)
  const [forecastLoading, setForecastLoading] = useState(false)

  const [retentionPct, setRetentionPct] = useState(50)
  const [churnCustomers, setChurnCustomers] = useState<ChurnCustomerRow[] | null>(null)

  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setForecastLoading(true)
    getForecast(periods)
      .then((res) => setForecast(res.forecast))
      .catch((err) => setError(String(err)))
      .finally(() => setForecastLoading(false))
  }, [periods])

  useEffect(() => {
    getChurn().then((res) => setChurnCustomers(res.customers)).catch((err) => setError(String(err)))
  }, [])

  const baselineTotal = forecast ? forecast.reduce((sum, row) => sum + row.forecast_revenue, 0) : 0
  const adjustedTotal = baselineTotal * (1 + growthAdjustmentPct / 100)

  const highRiskCustomers = churnCustomers?.filter((c) => c.churn_risk === "High Risk") ?? []
  const highRiskValue = highRiskCustomers.reduce((sum, c) => sum + (c.monetary ?? 0), 0)
  const revenueProtected = highRiskValue * (retentionPct / 100)

  return (
    <div className="p-8 space-y-6">
      <h1 className="text-3xl font-bold">Scenario Simulator</h1>
      {error && <p className="text-red-600">Error: {error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Revenue Forecast</CardTitle>
          <CardDescription>
            The horizon slider re-runs the real forecasting model live. The growth adjustment slider is a
            simple what-if multiplier layered on top of the model's output -- not a model re-run -- for
            exploring "what if we're off by X%" scenarios.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Forecast Horizon</Label>
              <span className="text-sm text-gray-500">{periods} month{periods !== 1 ? "s" : ""}</span>
            </div>
            <Slider
              value={[periods]}
              onValueChange={(value) => setPeriods(value[0])}
              min={1}
              max={24}
              step={1}
            />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>What-If Growth Adjustment</Label>
              <span className="text-sm text-gray-500">
                {growthAdjustmentPct > 0 ? "+" : ""}
                {growthAdjustmentPct}%
              </span>
            </div>
            <Slider
              value={[growthAdjustmentPct]}
              onValueChange={(value) => setGrowthAdjustmentPct(value[0])}
              min={-30}
              max={30}
              step={1}
            />
          </div>

          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <p className="text-sm text-gray-500">Model Baseline ({periods}-month total)</p>
              <p className="text-2xl font-bold">{forecastLoading ? "..." : formatCurrency(baselineTotal)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Adjusted Scenario Total</p>
              <p className="text-2xl font-bold">{forecastLoading ? "..." : formatCurrency(adjustedTotal)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Churn Retention Scenario</CardTitle>
          <CardDescription>
            Based on real churn-risk scoring: {highRiskCustomers.length} customers are currently flagged
            High Risk, representing {formatCurrency(highRiskValue)} in historical revenue. Adjust the
            slider to see how much of that could be protected at different retention-intervention rates.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Assumed Retention Rate from Intervention</Label>
              <span className="text-sm text-gray-500">{retentionPct}%</span>
            </div>
            <Slider
              value={[retentionPct]}
              onValueChange={(value) => setRetentionPct(value[0])}
              min={0}
              max={100}
              step={5}
            />
          </div>

          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <p className="text-sm text-gray-500">Total Revenue At Risk</p>
              <p className="text-2xl font-bold">{formatCurrency(highRiskValue)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Estimated Revenue Protected</p>
              <p className="text-2xl font-bold text-green-600">{formatCurrency(revenueProtected)}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}