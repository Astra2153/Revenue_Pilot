import { useEffect, useState } from "react"
import { getFinanceRaw, type FinanceRow } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  BarChart, Bar, Cell, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function formatCurrency(value: number) {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}
function compactCurrency(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value.toFixed(0)}`
}
function formatMonth(month: string) {
  return new Date(month).toLocaleDateString(undefined, { month: "short", year: "2-digit" })
}
const TOOLTIP_STYLE = { borderRadius: 12, border: "1px solid var(--rp-hairline)", fontSize: 12 }

export default function FinancePage() {
  const [rows, setRows] = useState<FinanceRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getFinanceRaw().then((res) => setRows(res.rows)).catch((err) => setError(String(err)))
  }, [])

  const sorted = [...rows].sort((a, b) => a.month.localeCompare(b.month))
  const withLabels = sorted.map((r) => ({ ...r, monthLabel: formatMonth(r.month) }))
  const last6 = withLabels.slice(-6)
  const marginSeries = withLabels.map((r) => ({
    monthLabel: r.monthLabel,
    grossMarginPct: r.revenue ? (r.gross_profit / r.revenue) * 100 : 0,
    operatingMarginPct: r.revenue ? (r.operating_profit / r.revenue) * 100 : 0,
  }))
  const latest = sorted[sorted.length - 1]

  /* ~24 monthly points would print every label on top of the next one.
     Showing every third keeps the axis readable without dropping data. */
  const denseTickInterval = Math.max(0, Math.floor(withLabels.length / 8))

  return (
    <div className="p-8 space-y-6 max-w-[1500px]">
      <div>
        <p className="rp-eyebrow mb-1">Analytics</p>
        <h1 className="text-3xl font-semibold">Finance</h1>
      </div>

      {error && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{error}</p>}

      {latest && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="rp-card-dark">
            <CardHeader className="pb-1">
              <p className="rp-eyebrow">Latest revenue</p>
              <CardTitle className="rp-stat text-3xl">{compactCurrency(latest.revenue)}</CardTitle>
            </CardHeader>
          </Card>
          <Card className="rp-card">
            <CardHeader className="pb-1">
              <CardDescription>Gross margin</CardDescription>
              <CardTitle className="rp-stat text-3xl">
                {((latest.gross_profit / latest.revenue) * 100).toFixed(1)}%
              </CardTitle>
            </CardHeader>
          </Card>
          <Card className="rp-card">
            <CardHeader className="pb-1">
              <CardDescription>Operating margin</CardDescription>
              <CardTitle className="rp-stat text-3xl">
                {((latest.operating_profit / latest.revenue) * 100).toFixed(1)}%
              </CardTitle>
            </CardHeader>
          </Card>
          <Card className="rp-card">
            <CardHeader className="pb-1">
              <CardDescription>Latest cash flow</CardDescription>
              <CardTitle className="rp-stat text-3xl">{compactCurrency(latest.cash_flow)}</CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <Card className="rp-card rp-chartbox">
        <CardHeader>
          <CardTitle className="text-lg">Where the revenue goes</CardTitle>
          <CardDescription>Revenue against each cost line, last six months</CardDescription>
        </CardHeader>
        <CardContent style={{ height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={last6} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
              <XAxis dataKey="monthLabel" tickLine={false} axisLine={false} />
              <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={56} />
              <Tooltip formatter={(v: any) => formatCurrency(Number(v))} contentStyle={TOOLTIP_STYLE} />
              <Legend />
              <Bar dataKey="revenue" name="Revenue" fill="var(--rp-ink)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="cogs" name="Cost of goods" fill="var(--rp-signal)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="marketing_spend" name="Marketing" fill="var(--rp-bloom)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="other_opex" name="Other opex" fill="#CFC9D2" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="rp-card rp-chartbox">
          <CardHeader>
            <CardTitle className="text-lg">Margins over time</CardTitle>
            <CardDescription>Gross and operating margin, month by month</CardDescription>
          </CardHeader>
          <CardContent style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={marginSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
                <XAxis dataKey="monthLabel" interval={denseTickInterval} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
                <Tooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} contentStyle={TOOLTIP_STYLE} />
                <Legend />
                <Line type="monotone" dataKey="grossMarginPct" name="Gross margin" stroke="var(--rp-ink)" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="operatingMarginPct" name="Operating margin" stroke="var(--rp-signal)" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="rp-card rp-chartbox">
          <CardHeader>
            <CardTitle className="text-lg">Monthly cash flow</CardTitle>
            <CardDescription>Red marks any month that ran cash-negative</CardDescription>
          </CardHeader>
          <CardContent style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={withLabels} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
                <XAxis dataKey="monthLabel" interval={denseTickInterval} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={56} />
                <Tooltip formatter={(v: any) => formatCurrency(Number(v))} contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="cash_flow" name="Cash flow" radius={[6, 6, 0, 0]}>
                  {withLabels.map((r) => (
                    <Cell key={r.month} fill={r.cash_flow >= 0 ? "var(--rp-ink)" : "var(--rp-signal)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card className="rp-card">
        <CardHeader>
          <CardTitle className="text-lg">Month by month</CardTitle>
          <CardDescription>Newest first</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Month</TableHead>
                  <TableHead className="text-right">Revenue</TableHead>
                  <TableHead className="text-right">Cost of goods</TableHead>
                  <TableHead className="text-right">Marketing</TableHead>
                  <TableHead className="text-right">Other opex</TableHead>
                  <TableHead className="text-right">Operating profit</TableHead>
                  <TableHead className="text-right">Cash flow</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {withLabels.slice().reverse().map((r) => (
                  <TableRow key={r.month}>
                    <TableCell className="font-medium">{r.monthLabel}</TableCell>
                    <TableCell className="text-right">{formatCurrency(r.revenue)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(r.cogs)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(r.marketing_spend)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(r.other_opex)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(r.operating_profit)}</TableCell>
                    <TableCell className="text-right" style={{ color: r.cash_flow < 0 ? "var(--rp-signal)" : undefined }}>
                      {formatCurrency(r.cash_flow)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}