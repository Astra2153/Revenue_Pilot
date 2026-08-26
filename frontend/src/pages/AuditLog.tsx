import { useEffect, useState } from "react"
import { getAuditLog, type AuditLogEntry } from "@/lib/api"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const ALL_TABLES = "all"
const TABLE_OPTIONS = [
  { value: ALL_TABLES, label: "All Tables" },
  { value: "employees", label: "Employees" },
  { value: "crm_deals", label: "CRM Deals" },
  { value: "crm_accounts", label: "CRM Accounts" },
]

function actionBadgeVariant(action: string) {
  if (action === "insert") return "default"
  if (action === "update") return "secondary"
  if (action === "delete") return "destructive"
  return "outline"
}

function formatTimestamp(iso: string) {
  return new Date(iso).toLocaleString()
}

/** Shows only the fields that actually changed between old_data and new_data. */
function diffFields(oldData: Record<string, unknown> | null, newData: Record<string, unknown> | null) {
  if (!oldData || !newData) return null
  const changed: { field: string; from: unknown; to: unknown }[] = []
  const keys = new Set([...Object.keys(oldData), ...Object.keys(newData)])
  for (const key of keys) {
    if (key === "updated_at" || key === "created_at") continue
    if (JSON.stringify(oldData[key]) !== JSON.stringify(newData[key])) {
      changed.push({ field: key, from: oldData[key], to: newData[key] })
    }
  }
  return changed
}

export default function AuditLog() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [tableFilter, setTableFilter] = useState(ALL_TABLES)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    getAuditLog(tableFilter === ALL_TABLES ? undefined : tableFilter)
      .then(setEntries)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [tableFilter])

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Audit Log</h1>
        <Select value={tableFilter} onValueChange={setTableFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TABLE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error && <p className="text-red-600">Error: {error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Recent Changes</CardTitle>
          <CardDescription>
            Every insert, update, and delete across employees and CRM deals/accounts. CRM changes are
            captured automatically by a database trigger; employee changes are logged from the Admin
            Portal. Click a row to see exactly what changed. "employee_name" reflects who the change was
            about (or, for CRM deals, who owned the deal) -- not who performed the action, since there is
            no authenticated login yet to attribute that to.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && <p className="text-gray-400 text-sm">Loading...</p>}
          {!loading && entries.length === 0 && (
            <p className="text-gray-400 text-sm">No audit entries found for this filter.</p>
          )}
          {!loading && entries.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Table</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Related To</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => {
                  const isExpanded = expandedId === entry.id
                  const changed = diffFields(entry.old_data, entry.new_data)
                  return (
                    <>
                      <TableRow
                        key={entry.id}
                        className="cursor-pointer hover:bg-gray-50"
                        onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                      >
                        <TableCell className="text-sm">{formatTimestamp(entry.created_at)}</TableCell>
                        <TableCell className="font-mono text-sm">{entry.table_name}</TableCell>
                        <TableCell>
                          <Badge variant={actionBadgeVariant(entry.action)}>{entry.action}</Badge>
                        </TableCell>
                        <TableCell>{entry.employee_name ?? "--"}</TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow key={`${entry.id}-detail`}>
                          <TableCell colSpan={4} className="bg-gray-50">
                            {entry.action === "update" && changed && changed.length > 0 && (
                              <div className="space-y-1 py-2">
                                <p className="text-sm font-medium mb-2">Changed fields:</p>
                                {changed.map((c) => (
                                  <div key={c.field} className="text-sm font-mono">
                                    <span className="text-gray-500">{c.field}:</span>{" "}
                                    <span className="text-red-600">{JSON.stringify(c.from)}</span>
                                    {" -> "}
                                    <span className="text-green-600">{JSON.stringify(c.to)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {entry.action === "insert" && (
                              <pre className="text-xs overflow-auto max-h-48 py-2">
                                {JSON.stringify(entry.new_data, null, 2)}
                              </pre>
                            )}
                            {entry.action === "delete" && (
                              <pre className="text-xs overflow-auto max-h-48 py-2">
                                {JSON.stringify(entry.old_data, null, 2)}
                              </pre>
                            )}
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
