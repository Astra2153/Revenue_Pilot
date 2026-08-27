import { useEffect, useState } from "react"
import {
  getSegments, getSegmentsSummary, getChurn,
  type RFMCustomer, type SegmentSummaryRow, type ChurnCustomerRow,
} from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ScatterChart, Scatter, PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

/* Segment colours run along the brand's crimson-to-pink axis rather
   than a rainbow, so the chart still reads as part of this product. */
const SEGMENT_COLORS = ["#D91E48", "#EC4899", "#F9A8C4", "#14131A", "#8B5CF6", "#0EA5E9"]
const RISK_COLORS: Record<string, string> = {
  "Low Risk": "#14131A",
  "Medium Risk": "#F9A8C4",
  "High Risk": "#D91E48",
}
const TOOLTIP_STYLE = { borderRadius: 12, border: "1px solid var(--rp-hairline)", fontSize: 12 }

function formatCurrency(value: number) {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}
function compactCurrency(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value.toFixed(0)}`
}

export default function CustomerIntelligence() {
  const [rfm, setRfm] = useState<RFMCustomer[]>([])
  const [summary, setSummary] = useState<SegmentSummaryRow[]>([])
  const [churn, setChurn] = useState<ChurnCustomerRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSegments().then((res) => setRfm(res.customers)).catch((err) => setError(String(err)))
    getSegmentsSummary().then((res) => setSummary(res.summary)).catch((err) => setError(String(err)))
    getChurn().then((res) => setChurn(res.customers)).catch((err) => setError(String(err)))
  }, [])

  const segmentGroups = Array.from(new Set(rfm.map((c) => c.segment_label)))
  const pieData = summary.map((s) => ({ name: s.segment_label, value: s.customers }))
  const riskCounts = ["Low Risk", "Medium Risk", "High Risk"].map((risk) => ({
    risk,
    count: churn.filter((c) => c.churn_risk === risk).length,
  }))
  const highRiskCustomers = churn.filter((c) => c.churn_risk === "High Risk")
  const highRisk = [...highRiskCustomers].sort((a, b) => b.monetary - a.monetary).slice(0, 10)
  const atStake = highRiskCustomers.reduce((s, c) => s + c.monetary, 0)

  return (
    <div className="p-8 space-y-6 max-w-[1500px]">
      <div>
        <p className="rp-eyebrow mb-1">Analytics</p>
        <h1 className="text-3xl font-semibold">Customers</h1>
      </div>

      {error && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{error}</p>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>Total customers</CardDescription>
            <CardTitle className="rp-stat text-3xl">{rfm.length || "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>Segments found</CardDescription>
            <CardTitle className="rp-stat text-3xl">{segmentGroups.length || "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>High churn risk</CardDescription>
            <CardTitle className="rp-stat text-3xl">{highRiskCustomers.length || "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card-dark">
          <CardHeader className="pb-1">
            <p className="rp-eyebrow">Revenue at stake</p>
            <CardTitle className="rp-stat text-3xl">{atStake ? compactCurrency(atStake) : "--"}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="rp-card rp-chartbox lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-lg">Who's worth what, and who's drifting</CardTitle>
            <CardDescription>
              Days since last purchase against lifetime spend. Bubble size is how often they buy.
              Anything far right has gone quiet.
            </CardDescription>
          </CardHeader>
          <CardContent style={{ height: 400 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" />
                <XAxis
                  type="number" dataKey="recency_days" name="Days since last purchase"
                  tickLine={false} axisLine={false}
                  label={{ value: "Days since last purchase", position: "insideBottom", offset: -14, fontSize: 11, fill: "var(--rp-slate)" }}
                />
                <YAxis
                  type="number" dataKey="monetary" name="Lifetime spend"
                  tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={56}
                />
                <ZAxis type="number" dataKey="frequency" range={[30, 260]} name="Orders" />
                <Tooltip
                  cursor={{ strokeDasharray: "3 3" }}
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value: any, name: any) =>
                    name === "Lifetime spend" ? formatCurrency(Number(value)) : value
                  }
                />
                <Legend verticalAlign="top" height={30} />
                {segmentGroups.map((seg, i) => (
                  <Scatter
                    key={seg}
                    name={seg}
                    data={rfm.filter((c) => c.segment_label === seg)}
                    fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]}
                    fillOpacity={0.75}
                  />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="rp-card rp-chartbox lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg">Segment mix</CardTitle>
            <CardDescription>Share of the customer base</CardDescription>
          </CardHeader>
          <CardContent style={{ height: 400 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={64} outerRadius={112} paddingAngle={2}>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any) => `${v} customers`} />
                <Legend verticalAlign="bottom" height={48} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="rp-card lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-lg">Segment summary</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Segment</TableHead>
                  <TableHead className="text-right">Customers</TableHead>
                  <TableHead className="text-right">Avg days since order</TableHead>
                  <TableHead className="text-right">Avg orders</TableHead>
                  <TableHead className="text-right">Segment value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.map((s) => (
                  <TableRow key={s.segment_label}>
                    <TableCell className="font-medium">{s.segment_label}</TableCell>
                    <TableCell className="text-right">{s.customers}</TableCell>
                    <TableCell className="text-right">{s.avg_recency_days.toFixed(0)}</TableCell>
                    <TableCell className="text-right">{s.avg_frequency.toFixed(1)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(s.total_monetary)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="rp-card rp-chartbox lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg">Churn risk spread</CardTitle>
          </CardHeader>
          <CardContent style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskCounts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
                <XAxis dataKey="risk" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} width={36} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any) => `${v} customers`} />
                <Bar dataKey="count" name="Customers" radius={[6, 6, 0, 0]}>
                  {riskCounts.map((r) => (
                    <Cell key={r.risk} fill={RISK_COLORS[r.risk]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card className="rp-card">
        <CardHeader>
          <CardTitle className="text-lg">Worth calling first</CardTitle>
          <CardDescription>Highest-spending customers currently flagged high risk</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Days since order</TableHead>
                <TableHead className="text-right">Lifetime spend</TableHead>
                <TableHead className="text-right">Churn probability</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {highRisk.map((c) => (
                <TableRow key={c.customer_id}>
                  <TableCell className="font-medium rp-mono">{c.customer_id}</TableCell>
                  <TableCell className="text-right">{String(c.recency_days ?? "\u2014")}</TableCell>
                  <TableCell className="text-right">{formatCurrency(c.monetary)}</TableCell>
                  <TableCell className="text-right">
                    <span className="rp-chip rp-chip--down">{(c.churn_probability * 100).toFixed(0)}%</span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}