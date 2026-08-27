import { useEffect, useState } from "react"
import {
  getEmployees,
  getDepartments,
  createEmployee,
  updateEmployee,
  deleteEmployee,
  getLeaderboard,
  getAdminSessions,
  type Employee,
  type Department,
  type LeaderboardResponse,
  type AdminSessionEntry,
} from "@/lib/api"
import AdminLoginGate from "@/components/AdminLoginGate"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts"

const ROLES = ["admin", "manager", "employee"]
const NO_DEPARTMENT = "none"
const UNLOCK_KEY = "rp_admin_unlocked"

interface FormState {
  fullName: string
  email: string
  role: string
  departmentId: string
}
const EMPTY_FORM: FormState = { fullName: "", email: "", role: "employee", departmentId: NO_DEPARTMENT }

function compactCurrency(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value.toFixed(0)}`
}
function shortName(name: string) {
  return name.replace(/^Rep - /, "")
}
function formatTimestamp(iso: string) {
  return new Date(iso).toLocaleString()
}

export default function AdminPortal() {
  /* sessionStorage, not localStorage: the unlock lasts while this tab is
     open and is gone when it closes. The passkey itself is never stored --
     only the fact that the server accepted it. */
  const [unlocked, setUnlocked] = useState(() => sessionStorage.getItem(UNLOCK_KEY) === "1")

  function handleUnlock() {
    sessionStorage.setItem(UNLOCK_KEY, "1")
    setUnlocked(true)
  }
  function handleLock() {
    sessionStorage.removeItem(UNLOCK_KEY)
    setUnlocked(false)
  }

  if (!unlocked) return <AdminLoginGate onUnlock={handleUnlock} />
  return <AdminPortalContent onLock={handleLock} />
}

function AdminPortalContent({ onLock }: { onLock: () => void }) {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null)
  const [sessions, setSessions] = useState<AdminSessionEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  function loadData() {
    getEmployees().then(setEmployees).catch((err) => setError(String(err)))
    getDepartments().then(setDepartments).catch((err) => setError(String(err)))
    getLeaderboard().then(setLeaderboard).catch((err) => setError(String(err)))
    getAdminSessions(25).then(setSessions).catch((err) => setError(String(err)))
  }

  useEffect(() => {
    loadData()
  }, [])

  function openCreateDialog() {
    setEditingEmployee(null)
    setForm(EMPTY_FORM)
    setDialogOpen(true)
  }

  function openEditDialog(emp: Employee) {
    setEditingEmployee(emp)
    setForm({
      fullName: emp.full_name,
      email: emp.email,
      role: emp.role,
      departmentId: emp.department_id ?? NO_DEPARTMENT,
    })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    setSaving(true)
    setError(null)
    const payload = {
      full_name: form.fullName,
      email: form.email,
      role: form.role,
      department_id: form.departmentId === NO_DEPARTMENT ? null : form.departmentId,
    }
    try {
      if (editingEmployee) {
        await updateEmployee(editingEmployee.id, payload)
      } else {
        await createEmployee(payload)
      }
      setDialogOpen(false)
      loadData()
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(emp: Employee) {
    if (!window.confirm(`Remove ${emp.full_name}? This can't be undone.`)) return
    try {
      await deleteEmployee(emp.id)
      loadData()
    } catch (err) {
      setError(String(err))
    }
  }

  /* Raw won value beside difficulty-adjusted value. Where the two bars
     disagree is exactly where naive "who closed the most" ranking would
     have misjudged someone. */
  const perfData = (leaderboard?.employees ?? [])
    .filter((e) => e.raw.total_deals > 0)
    .map((e) => ({
      name: shortName(e.full_name),
      raw: Math.round(e.raw.total_won_value),
      adjusted: Math.round(e.normalized.difficulty_adjusted_value),
      index: e.normalized.relative_contribution_index,
    }))

  return (
    <div className="p-8 space-y-6 max-w-[1500px]">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="rp-eyebrow mb-1">Operations</p>
          <h1 className="text-3xl font-semibold">Admin</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onLock}>Lock</Button>
          <Button onClick={openCreateDialog}>Add employee</Button>
        </div>
      </div>

      {error && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{error}</p>}

      <Card className="rp-card rp-chartbox">
        <CardHeader>
          <CardTitle className="text-lg">Sales performance, raw against adjusted</CardTitle>
          <CardDescription>
            Adjusted value weights each win by how hard that account segment is to close. Where the two
            bars diverge is where ranking on raw totals alone would have misread someone.
          </CardDescription>
        </CardHeader>
        <CardContent style={{ height: 340 }}>
          {perfData.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--rp-faint)" }}>No deal data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perfData} margin={{ top: 8, right: 8, bottom: 40, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--rp-hairline)" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} angle={-18} textAnchor="end" height={60} interval={0} />
                <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={56} />
                <Tooltip
                  formatter={(v: any) => compactCurrency(Number(v))}
                  contentStyle={{ borderRadius: 12, border: "1px solid var(--rp-hairline)", fontSize: 12 }}
                />
                <Legend />
                <Bar dataKey="raw" name="Raw won value" fill="var(--rp-signal-dim)" radius={[6, 6, 0, 0]} />
                <Bar dataKey="adjusted" name="Difficulty-adjusted" fill="var(--rp-signal)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card className="rp-card">
        <CardHeader>
          <CardTitle className="text-lg">Employees</CardTitle>
          <CardDescription>Add people, change their role, or move them between departments.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Department</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {employees.map((emp) => (
                <TableRow key={emp.id}>
                  <TableCell className="font-medium">{emp.full_name}</TableCell>
                  <TableCell style={{ color: "var(--rp-slate)" }}>{emp.email}</TableCell>
                  <TableCell><Badge variant="outline">{emp.role}</Badge></TableCell>
                  <TableCell>{emp.department ?? "\u2014"}</TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button variant="secondary" size="sm" onClick={() => openEditDialog(emp)}>Edit</Button>
                    <Button variant="destructive" size="sm" onClick={() => handleDelete(emp)}>Remove</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card className="rp-card">
        <CardHeader>
          <CardTitle className="text-lg">Admin access log</CardTitle>
          <CardDescription>
            Every unlock attempt, successful or not, with the browser it came from. One shared passkey
            can't tell you which person it was, only which device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sessions.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--rp-faint)" }}>No access recorded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>Device</TableHead>
                  <TableHead>IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="text-sm">{formatTimestamp(s.created_at)}</TableCell>
                    <TableCell>
                      <span className={`rp-chip ${s.action === "login_success" ? "rp-chip--up" : "rp-chip--down"}`}>
                        {s.action === "login_success" ? "Granted" : "Denied"}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">{s.new_data?.device ?? "\u2014"}</TableCell>
                    <TableCell className="text-sm rp-mono">{s.new_data?.ip_address ?? "\u2014"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingEmployee ? "Edit employee" : "Add employee"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="fullName">Full name</Label>
              <Input id="fullName" value={form.fullName} onChange={(e) => setForm({ ...form, fullName: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={form.role} onValueChange={(value) => setForm({ ...form, role: value })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((role) => <SelectItem key={role} value={role}>{role}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Department</Label>
              <Select value={form.departmentId} onValueChange={(value) => setForm({ ...form, departmentId: value })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_DEPARTMENT}>None</SelectItem>
                  {departments.map((dept) => <SelectItem key={dept.id} value={dept.id}>{dept.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={saving || !form.fullName || !form.email}>
              {saving ? "Saving\u2026" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}