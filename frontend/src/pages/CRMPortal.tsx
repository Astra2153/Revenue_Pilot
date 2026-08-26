import { useEffect, useState } from "react"
import {
  getCompanyKPI,
  getLeaderboard,
  getFairnessAudit,
  getEmployeeKPI,
  type CompanyKPIResponse,
  type LeaderboardResponse,
  type FairnessAuditResponse,
  type EmployeeDetailResponse,
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

function fairnessBadgeVariant(status: string) {
  if (status === "passed") return "default"
  if (status === "flagged_low_confidence") return "secondary"
  if (status === "flagged") return "destructive"
  return "outline"
}

export default function CRMPortal() {
  const [company, setCompany] = useState<CompanyKPIResponse | null>(null)
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null)
  const [fairness, setFairness] = useState<FairnessAuditResponse | null>(null)
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeDetailResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCompanyKPI().then(setCompany).catch((err) => setError(String(err)))
    getLeaderboard().then(setLeaderboard).catch((err) => setError(String(err)))
    getFairnessAudit().then(setFairness).catch((err) => setError(String(err)))
  }, [])

  function handleRowClick(employeeId: string) {
    getEmployeeKPI(employeeId).then(setSelectedEmployee).catch((err) => setError(String(err)))
  }

  const crm = company?.crm as Record<string, unknown> | undefined

  return (
    <div className="p-8 space-y-6">
      <h1 className="text-3xl font-bold">CRM Portal</h1>
      {error && <p className="text-red-600">Error: {error}</p>}

      {/* Company-wide CRM summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Deals</CardDescription>
            <CardTitle className="text-2xl">{(crm?.total_deals as number) ?? "--"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Win Rate</CardDescription>
            <CardTitle className="text-2xl">
              {crm?.win_rate_pct !== undefined ? `${crm.win_rate_pct}%` : "--"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Won Value</CardDescription>
            <CardTitle className="text-2xl">{formatCurrency(crm?.total_won_value as number)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Open Deals</CardDescription>
            <CardTitle className="text-2xl">{(crm?.open_deals as number) ?? "--"}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Fairness audit banner */}
      {fairness && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <CardTitle>Fairness Audit</CardTitle>
              <Badge variant={fairnessBadgeVariant(fairness.status)}>{fairness.status}</Badge>
            </div>
            <CardDescription>
              {fairness.interpretation ?? fairness.reason ?? "No further detail available."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Leaderboard */}
      <Card>
        <CardHeader>
          <CardTitle>Sales Leaderboard</CardTitle>
          <CardDescription>
            Raw and difficulty-adjusted metrics side by side. Sorted by difficulty-adjusted value. Click a row for detail.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {leaderboard?.note && <p className="text-gray-500">{leaderboard.note}</p>}
          {leaderboard && leaderboard.employees.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Deals</TableHead>
                  <TableHead>Win Rate</TableHead>
                  <TableHead>Raw Won Value</TableHead>
                  <TableHead>Adjusted Value</TableHead>
                  <TableHead>Relative Index</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leaderboard.employees.map((emp) => (
                  <TableRow
                    key={emp.employee_id}
                    className="cursor-pointer hover:bg-gray-50"
                    onClick={() => handleRowClick(emp.employee_id)}
                  >
                    <TableCell className="font-medium">{emp.full_name}</TableCell>
                    <TableCell>{emp.raw.total_deals}</TableCell>
                    <TableCell>{emp.raw.win_rate_pct !== null ? `${emp.raw.win_rate_pct}%` : "--"}</TableCell>
                    <TableCell>{formatCurrency(emp.raw.total_won_value)}</TableCell>
                    <TableCell>{formatCurrency(emp.normalized.difficulty_adjusted_value)}</TableCell>
                    <TableCell>{emp.normalized.relative_contribution_index.toFixed(2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Selected employee detail */}
      {selectedEmployee && (
        <Card>
          <CardHeader>
            <CardTitle>{selectedEmployee.full_name}</CardTitle>
            <CardDescription>
              {selectedEmployee.sufficient_data ? "Sufficient data for assessment" : "Limited data on record"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p>{selectedEmployee.narrative}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}