import { useEffect, useState } from "react"
import {
  getCompanyKPI,
  getInsights,
  getFinanceRaw,
  getMarketingROI,
  type CompanyKPIResponse,
  type InsightsResponse,
  type FinanceRow,
  type MarketingROIResponse,
} from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"

function splitCurrency(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return { major: "--", minor: "" }
  const [whole, cents] = Math.abs(value).toFixed(2).split(".")
  const sign = value < 0 ? "-" : ""
  return { major: `${sign}$${Number(whole).toLocaleString()}`, minor: `.${cents}` }
}
function compactCurrency(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value.toFixed(0)}`
}
function formatMonth(month: string) {
  return new Date(month).toLocaleDateString(undefined, { month: "short", year: "2-digit" })
}

export default function Dashboard() {
  const [company, setCompany] = useState<CompanyKPIResponse | null>(null)
  const [insights, setInsights] = useState<InsightsResponse | null>(null)
  const [finance, setFinance] = useState<FinanceRow[]>([])
  const [roi, setRoi] = useState<MarketingROIResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCompanyKPI().then(setCompany).catch((e) => setError(String(e)))
    getInsights().then(setInsights).catch((e) => setError(String(e)))
    getFinanceRaw().then((r) => setFinance(r.rows)).catch((e) => setError(String(e)))
    getMarketingROI().then(setRoi).catch((e) => setError(String(e)))
  }, [])

  const fin = company?.finance as Record<string, unknown> | undefined
  const cust = company?.customer as Record<string, unknown> | undefined
  const crm = company?.crm as Record<string, unknown> | undefined

  const revenue = fin?.revenue as number | undefined
  const momPct = fin?.revenue_mom_pct as number | undefined
  const rev = splitCurrency(revenue)

  const trend = [...finance]
    .sort((a, b) => a.month.localeCompare(b.month))
    .slice(-12)
    .map((r) => ({ label: formatMonth(r.month), revenue: r.revenue, profit: r.operating_profit }))

  const channels = roi
    ? [...roi.channels].sort((a, b) => b.roi_multiple - a.roi_multiple).map((c) => ({
        channel: c.channel,
        roi: Number(c.roi_multiple.toFixed(1)),
      }))
    : []

  const insightGroups: { key: string; title: string }[] = [
    { key: "sales", title: "Sales" },
    { key: "finance", title: "Finance" },
    { key: "marketing", title: "Marketing" },
    { key: "customer", title: "Customers" },
  ]

  return (
    <div className="p-8 space-y-6 max-w-[1500px]">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="rp-eyebrow mb-1">Overview</p>
          <h1 className="text-3xl font-semibold">Business health</h1>
        </div>
        <p className="text-sm" style={{ color: "var(--rp-slate)" }}>
          Period: {(fin?.period as string) ?? "\u2014"}
        </p>
      </div>

      {error && (
        <Card className="rp-card">
          <CardContent className="pt-6">
            <p className="text-sm" style={{ color: "var(--rp-signal)" }}>
              Couldn't reach the API. {error}
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--rp-slate)" }}>
              The backend sleeps after inactivity on the free tier. Wait about a minute and refresh.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Hero: the one number that matters, plus its movement. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="rp-card lg:col-span-2">
          <CardHeader className="pb-2">
            <CardDescription>Monthly revenue</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-3 flex-wrap">
              <span className="rp-stat text-5xl">
                {rev.major}
                <span className="rp-stat-minor text-3xl">{rev.minor}</span>
              </span>
              {momPct !== undefined && (
                <span className={`rp-chip ${momPct >= 0 ? "rp-chip--up" : "rp-chip--down"} mb-1.5`}>
                  {momPct >= 0 ? "\u2191" : "\u2193"} {Math.abs(momPct).toFixed(1)}% MoM
                </span>
              )}
            </div>
            <div className="mt-5 rp-chartbox" style={{ height: 190 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--rp-signal)" stopOpacity={0.22} />
                      <stop offset="100%" stopColor="var(--rp-signal)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={52} />
                  <Tooltip
                    formatter={(v: any) => compactCurrency(Number(v))}
                    contentStyle={{ borderRadius: 12, border: "1px solid var(--rp-hairline)", fontSize: 12 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="revenue"
                    stroke="var(--rp-signal)"
                    strokeWidth={2.5}
                    fill="url(#revFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* The single dark card: contrast anchor for the screen. */}
        <Card className="rp-card-dark flex flex-col justify-between">
          <CardHeader className="pb-2">
            <p className="rp-eyebrow">Operating margin</p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <span className="rp-stat text-5xl">
                {fin?.gross_margin_pct !== undefined
                  ? `${(((fin.operating_profit as number) / (fin.revenue as number)) * 100).toFixed(1)}%`
                  : "--"}
              </span>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span style={{ color: "#8E8A97" }}>Gross margin</span>
                <span className="rp-num font-medium">
                  {fin?.gross_margin_pct !== undefined ? `${fin.gross_margin_pct}%` : "--"}
                </span>
              </div>
              <div className="flex justify-between">
                <span style={{ color: "#8E8A97" }}>Operating profit</span>
                <span className="rp-num font-medium">
                  {fin?.operating_profit !== undefined ? compactCurrency(fin.operating_profit as number) : "--"}
                </span>
              </div>
              <div className="flex justify-between">
                <span style={{ color: "#8E8A97" }}>Cash flow</span>
                <span className="rp-num font-medium">
                  {fin?.cash_flow !== undefined ? compactCurrency(fin.cash_flow as number) : "--"}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Secondary KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>Customers</CardDescription>
            <CardTitle className="rp-stat text-3xl">{(cust?.total_customers as number) ?? "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>High churn risk</CardDescription>
            <CardTitle className="rp-stat text-3xl">
              {cust?.high_risk_churn_pct !== undefined ? `${cust.high_risk_churn_pct}%` : "--"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>Open deals</CardDescription>
            <CardTitle className="rp-stat text-3xl">{(crm?.open_deals as number) ?? "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="rp-card">
          <CardHeader className="pb-1">
            <CardDescription>Deal win rate</CardDescription>
            <CardTitle className="rp-stat text-3xl">
              {crm?.win_rate_pct !== undefined ? `${crm.win_rate_pct}%` : "--"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Channel returns */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="rp-card rp-chartbox lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-lg">Return by marketing channel</CardTitle>
            <CardDescription>Estimated revenue returned per dollar spent</CardDescription>
          </CardHeader>
          <CardContent style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={channels} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" horizontal={false} />
                <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => `${v}x`} />
                <YAxis type="category" dataKey="channel" width={116} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={(v: any) => `${v}x return`}
                  contentStyle={{ borderRadius: 12, border: "1px solid var(--rp-hairline)", fontSize: 12 }}
                />
                <Bar dataKey="roi" radius={[0, 6, 6, 0]}>
                  {channels.map((c, i) => (
                    <Cell key={c.channel} fill={i === 0 ? "var(--rp-signal)" : "var(--rp-signal-dim)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="rp-card lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg">What the numbers say</CardTitle>
            <CardDescription>Written from the data, not generated prose</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 max-h-[300px] overflow-y-auto">
            {insightGroups.map(({ key, title }) => {
              const bullets = (insights?.[key] as string[] | undefined) ?? []
              if (!bullets.length) return null
              return (
                <div key={key}>
                  <p className="rp-eyebrow mb-1.5">{title}</p>
                  <ul className="space-y-1.5">
                    {bullets.map((b, i) => (
                      <li key={i} className="text-sm leading-relaxed flex gap-2">
                        <span style={{ color: "var(--rp-signal)" }}>&bull;</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
            {!insights && <p className="text-sm" style={{ color: "var(--rp-faint)" }}>{"Loading insights\u2026"}</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}