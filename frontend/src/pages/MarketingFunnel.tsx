import { useEffect, useState } from "react"
import {
  getCompanyKPI,
  getMarketingROI,
  getMarketingAnomalies,
  type CompanyKPIResponse,
  type MarketingROIResponse,
  type MarketingAnomaliesResponse,
} from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "--"
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return "--"
  return `${(value * 100).toFixed(1)}%`
}

export default function MarketingFunnel() {
  const [company, setCompany] = useState<CompanyKPIResponse | null>(null)
  const [roi, setRoi] = useState<MarketingROIResponse | null>(null)
  const [anomalies, setAnomalies] = useState<MarketingAnomaliesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCompanyKPI().then(setCompany).catch((err) => setError(String(err)))
    getMarketingROI().then(setRoi).catch((err) => setError(String(err)))
    getMarketingAnomalies().then(setAnomalies).catch((err) => setError(String(err)))
  }, [])

  const marketing = company?.marketing as Record<string, unknown> | undefined

  return (
    <div className="p-8 space-y-6">
      <h1 className="text-3xl font-bold">Marketing Funnel</h1>
      {error && <p className="text-red-600">Error: {error}</p>}

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Period Spend</CardDescription>
            <CardTitle className="text-2xl">{formatCurrency(marketing?.period_spend as number)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Period Conversions</CardDescription>
            <CardTitle className="text-2xl">{(marketing?.period_conversions as number) ?? "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Best Channel</CardDescription>
            <CardTitle className="text-xl">{(marketing?.best_channel as string) ?? "--"}</CardTitle>
            <CardDescription>{(marketing?.best_channel_roi as number)?.toFixed(1)}x ROI</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Weakest Channel</CardDescription>
            <CardTitle className="text-xl">{(marketing?.weakest_channel as string) ?? "--"}</CardTitle>
            <CardDescription>{(marketing?.weakest_channel_roi as number)?.toFixed(1)}x ROI</CardDescription>
          </CardHeader>
        </Card>
      </div>

      {/* Channel funnel table */}
      <Card>
        <CardHeader>
          <CardTitle>Channel Performance</CardTitle>
          <CardDescription>
            Spend, leads, conversions, cost-per-acquisition, and estimated ROI multiple per channel -- sorted best to worst.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {roi && roi.channels.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>Spend</TableHead>
                  <TableHead>Leads</TableHead>
                  <TableHead>Conversions</TableHead>
                  <TableHead>Conv. Rate</TableHead>
                  <TableHead>CAC</TableHead>
                  <TableHead>Est. Value</TableHead>
                  <TableHead>ROI Multiple</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roi.channels.map((ch) => (
                  <TableRow key={ch.channel}>
                    <TableCell className="font-medium">{ch.channel}</TableCell>
                    <TableCell>{formatCurrency(ch.total_spend)}</TableCell>
                    <TableCell>{ch.total_leads}</TableCell>
                    <TableCell>{ch.total_conversions}</TableCell>
                    <TableCell>{formatPercent(ch.conversion_rate)}</TableCell>
                    <TableCell>{formatCurrency(ch.cac)}</TableCell>
                    <TableCell>{formatCurrency(ch.estimated_value_generated)}</TableCell>
                    <TableCell>
                      <Badge variant={ch.roi_multiple >= 1 ? "default" : "destructive"}>
                        {ch.roi_multiple.toFixed(1)}x
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Anomalies */}
      {anomalies && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <CardTitle>Flagged Anomalies</CardTitle>
              <Badge variant={anomalies.flagged_count > 0 ? "secondary" : "default"}>
                {anomalies.flagged_count} flagged
              </Badge>
            </div>
            <CardDescription>
              Months/channels statistically unusual relative to the rest of the marketing data (via IsolationForest).
            </CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}