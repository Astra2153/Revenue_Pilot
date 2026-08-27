const BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${await response.text()}`)
  }
  return response.json() as Promise<T>
}

export interface HealthResponse {
  status: string
}

export interface InsightsResponse {
  [key: string]: unknown
}

export function getHealth() {
  return apiFetch<HealthResponse>("/api/health")
}

export function getInsights() {
  return apiFetch<InsightsResponse>("/api/insights")
}

export interface CompanyKPIResponse {
  finance: Record<string, unknown>
  sales: Record<string, unknown>
  marketing: Record<string, unknown>
  customer: Record<string, unknown>
  finance_anomalies_total?: number
  crm: Record<string, unknown>
}

export interface EmployeeMetrics {
  employee_id: string
  full_name: string
  role: string
  raw: {
    total_deals: number
    closed_deals?: number
    won_deals: number
    win_rate_pct: number | null
    total_won_value: number
    avg_deal_value_won?: number | null
    segment_mix?: Record<string, number>
  }
  normalized: {
    difficulty_adjusted_value: number
    value_per_deal_worked: number
    relative_contribution_index: number
  }
  activity_count: number
  sufficient_data: boolean
}

export interface LeaderboardResponse {
  note?: string
  difficulty_weights: Record<string, number>
  segment_avg_deal_values: Record<string, number>
  employees: EmployeeMetrics[]
}

export interface EmployeeDetailResponse extends EmployeeMetrics {
  difficulty_weights_used: Record<string, number>
  narrative: string
}

export interface FairnessAuditResponse {
  status: string
  reason?: string
  group_sizes?: Record<string, number>
  group_means_by_dominant_segment?: Record<string, number>
  overall_mean?: number
  difficulty_weights_used?: Record<string, number>
  won_deal_counts_by_group?: Record<string, number>
  flagged_groups_undercorrected?: Record<string, number>
  flagged_groups_overcorrected?: Record<string, number>
  groups_excluded_too_small?: Record<string, number>
  interpretation?: string
}

export function getCompanyKPI() {
  return apiFetch<CompanyKPIResponse>("/api/kpi/company")
}

export function getLeaderboard() {
  return apiFetch<LeaderboardResponse>("/api/kpi/leaderboard")
}

export function getEmployeeKPI(employeeId: string) {
  return apiFetch<EmployeeDetailResponse>(`/api/kpi/employee/${employeeId}`)
}

export function getFairnessAudit() {
  return apiFetch<FairnessAuditResponse>("/api/kpi/fairness-audit")
}

export interface Department {
  id: string
  name: string
}

export interface Employee {
  id: string
  full_name: string
  email: string
  role: string
  department_id: string | null
  manager_id: string | null
  department: string | null
}

export interface EmployeeCreatePayload {
  full_name: string
  email: string
  role: string
  department_id?: string | null
  manager_id?: string | null
}

export type EmployeeUpdatePayload = Partial<EmployeeCreatePayload>

export function getDepartments() {
  return apiFetch<Department[]>("/api/departments")
}

export function getEmployees() {
  return apiFetch<Employee[]>("/api/employees")
}

export function createEmployee(payload: EmployeeCreatePayload) {
  return apiFetch<Employee>("/api/employees", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateEmployee(employeeId: string, payload: EmployeeUpdatePayload) {
  return apiFetch<Employee>(`/api/employees/${employeeId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteEmployee(employeeId: string) {
  return apiFetch<{ deleted: boolean; employee_id: string }>(`/api/employees/${employeeId}`, {
    method: "DELETE",
  })
}

export interface MarketingChannelROI {
  channel: string
  total_spend: number
  total_leads: number
  total_conversions: number
  cac: number | null
  estimated_value_generated: number
  roi_multiple: number
  conversion_rate: number | null
}

export interface MarketingROIResponse {
  channels: MarketingChannelROI[]
}

export interface MarketingAnomalyRow {
  [key: string]: unknown
  is_anomaly: boolean
  anomaly_score: number
}

export interface MarketingAnomaliesResponse {
  rows: MarketingAnomalyRow[]
  flagged_count: number
}

export function getMarketingROI() {
  return apiFetch<MarketingROIResponse>("/api/marketing/roi")
}

export function getMarketingAnomalies() {
  return apiFetch<MarketingAnomaliesResponse>("/api/anomalies/marketing")
}

export interface ForecastRow {
  month: string
  forecast_revenue: number
}

export interface ForecastResponse {
  metrics: { mae: number | null; r2: number | null; test_size: number }
  forecast: ForecastRow[]
  feature_importances: Record<string, unknown>[]
}

export interface ChurnCustomerRow {
  customer_id?: string
  monetary: number
  churn_probability: number
  churn_risk: string
  [key: string]: unknown
}

export interface ChurnResponse {
  metrics: Record<string, unknown>
  customers: ChurnCustomerRow[]
  feature_importances: Record<string, unknown>[]
}

export function getForecast(periods: number) {
  return apiFetch<ForecastResponse>(`/api/forecast?periods=${periods}`)
}

export function getChurn() {
  return apiFetch<ChurnResponse>("/api/churn")
}

export interface ChatResponse {
  response: string
  model_used: string | null
}

export function sendChatMessage(message: string, module: string | null) {
  return apiFetch<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, module }),
  })
}

export interface AuditLogEntry {
  id: string
  employee_id: string | null
  table_name: string
  record_id: string
  action: string
  old_data: Record<string, unknown> | null
  new_data: Record<string, unknown> | null
  created_at: string
  employee_name: string | null
}

export function getAuditLog(tableName?: string, limit = 200) {
  const params = new URLSearchParams()
  if (tableName) params.set("table_name", tableName)
  params.set("limit", String(limit))
  return apiFetch<AuditLogEntry[]>(`/api/audit-log?${params.toString()}`)
}

export interface NLQueryResponse {
  status: "ok" | "refused" | "error"
  question: string
  division?: string
  generated_sql?: string
  row_count?: number
  rows?: Record<string, unknown>[]
  truncated?: boolean
  answer?: string
  reason?: string
  error?: string
}

export interface QuerySchemaResponse {
  division: string
  tables: Record<string, unknown>
  max_rows: number
}

export function askQuery(question: string, division: string) {
  return apiFetch<NLQueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify({ question, division, explain: true }),
  })
}

export function getQuerySchema(division: string) {
  return apiFetch<QuerySchemaResponse>(`/api/query/schema?division=${division}`)
}

export interface FinanceRow {
  month: string
  revenue: number
  marketing_spend: number
  cogs: number
  gross_profit: number
  other_opex: number
  operating_profit: number
  cash_flow: number
}

export function getFinanceRaw() {
  return apiFetch<{ rows: FinanceRow[] }>("/api/finance/raw")
}

export interface SalesRow {
  transaction_id: string
  customer_id: string
  segment: string
  region: string
  date: string
  product_category: string
  sales_channel: string
  revenue: number
  units_sold: number
}

export function getSalesRaw() {
  return apiFetch<{ rows: SalesRow[] }>("/api/sales/raw?limit=5000")
}

export interface RFMCustomer {
  customer_id: string
  recency_days: number
  frequency: number
  monetary: number
  segment_label: string
  segment: string
  region: string
}

export function getSegments() {
  return apiFetch<{ customers: RFMCustomer[] }>("/api/segments")
}

export interface SegmentSummaryRow {
  segment_label: string
  customers: number
  avg_recency_days: number
  avg_frequency: number
  avg_monetary: number
  total_monetary: number
}

export function getSegmentsSummary() {
  return apiFetch<{ summary: SegmentSummaryRow[] }>("/api/segments/summary")
}

export interface AdminSessionEntry {
  id: string
  table_name: string
  record_id: string
  action: string
  new_data: { device?: string | null; ip_address?: string | null } | null
  created_at: string
}

/** Sends the passkey to the backend to be checked there, never in the browser. */
export function adminLogin(passkey: string, device: string) {
  return apiFetch<{ granted: boolean }>("/api/admin/login", {
    method: "POST",
    body: JSON.stringify({ passkey, device }),
  })
}

export function getAdminSessions(limit = 50) {
  return apiFetch<AdminSessionEntry[]>(`/api/admin/sessions?limit=${limit}`)
}