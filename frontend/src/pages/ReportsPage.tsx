import { useState } from "react"
import {
  getReportPreview,
  sendReport,
  sendReportToAllAdmins,
  type ReportPreviewResponse,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/** True when Resend's response has no error field -- Resend's own success
    shape varies, but every failure path in this app funnels into {error}. */
function wasSent(result: Record<string, unknown> | null | undefined): boolean {
  if (!result) return false
  if ("error" in result) return false
  if ("admin" in result) {
    const admin = result.admin as Record<string, unknown> | null
    return !!admin && !("error" in admin)
  }
  return true
}

export default function ReportsPage() {
  const [preview, setPreview] = useState<ReportPreviewResponse | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [emailInput, setEmailInput] = useState("")
  const [sending, setSending] = useState(false)
  const [sendResult, setSendResult] = useState<Record<string, unknown> | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)

  const [sendingAll, setSendingAll] = useState(false)
  const [sendAllResult, setSendAllResult] = useState<Record<string, unknown> | null>(null)
  const [sendAllError, setSendAllError] = useState<string | null>(null)

  function loadPreview() {
    setLoadingPreview(true)
    setPreviewError(null)
    getReportPreview()
      .then(setPreview)
      .catch((err) => setPreviewError(String(err)))
      .finally(() => setLoadingPreview(false))
  }

  async function handleSend() {
    const emails = emailInput.split(",").map((e) => e.trim()).filter(Boolean)
    if (!emails.length) return
    setSending(true)
    setSendError(null)
    setSendResult(null)
    try {
      const res = await sendReport(emails)
      setSendResult(res.send_result)
    } catch (err) {
      setSendError(String(err))
    } finally {
      setSending(false)
    }
  }

  async function handleSendAll() {
    setSendingAll(true)
    setSendAllError(null)
    setSendAllResult(null)
    try {
      const res = await sendReportToAllAdmins()
      setSendAllResult(res)
    } catch (err) {
      setSendAllError(String(err))
    } finally {
      setSendingAll(false)
    }
  }

  return (
    <div className="p-8 space-y-6 max-w-[1500px]">
      <div>
        <p className="rp-eyebrow mb-1">Tools</p>
        <h1 className="text-3xl font-semibold">Monthly Reports</h1>
      </div>

      <Card className="rp-card">
        <CardContent className="pt-6 text-sm" style={{ color: "var(--rp-slate)" }}>
          <strong style={{ color: "var(--rp-ink)" }}>About delivery:</strong> email is sent through
          Resend's free tier, which only delivers to the one address verified on the account -- other
          recipients will be accepted here but won't actually land in an inbox until a sending domain
          is verified. The preview and generated content below are real either way.
        </CardContent>
      </Card>

      <Card className="rp-card">
        <CardHeader>
          <CardTitle className="text-lg">Preview this month's report</CardTitle>
          <CardDescription>Builds the real narrative and HTML without sending anything.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button onClick={loadPreview} disabled={loadingPreview}>
            {loadingPreview ? "Generating\u2026" : preview ? "Regenerate preview" : "Generate preview"}
          </Button>
          {previewError && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{previewError}</p>}
          {preview && (
            <div className="space-y-4">
              <div>
                <p className="rp-eyebrow mb-1.5">Narrative</p>
                <p className="text-sm leading-relaxed">{preview.narrative}</p>
              </div>
              <div>
                <p className="rp-eyebrow mb-1.5">Why it happened</p>
                <p className="text-sm leading-relaxed">{preview.causal_narrative}</p>
              </div>
              <div>
                <p className="rp-eyebrow mb-1.5">Rendered email</p>
                <iframe
                  title="Report preview"
                  srcDoc={preview.html}
                  className="w-full rounded-lg border"
                  style={{ height: 520, borderColor: "var(--rp-hairline)" }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="rp-card">
          <CardHeader>
            <CardTitle className="text-lg">Send to specific addresses</CardTitle>
            <CardDescription>Comma-separated if more than one.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="emails">Recipients</Label>
              <Input
                id="emails"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                placeholder="someone@example.com"
                disabled={sending}
              />
            </div>
            <Button onClick={handleSend} disabled={sending || !emailInput.trim()}>
              {sending ? "Sending\u2026" : "Send report"}
            </Button>
            {sendError && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{sendError}</p>}
            {sendResult && (
              <div className="space-y-2 pt-2">
                <span className={`rp-chip ${wasSent(sendResult) ? "rp-chip--up" : "rp-chip--down"}`}>
                  {wasSent(sendResult) ? "Accepted by Resend" : "Not sent"}
                </span>
                <pre className="text-xs rounded-md p-3 overflow-x-auto" style={{ background: "var(--rp-canvas)" }}>
                  {JSON.stringify(sendResult, null, 2)}
                </pre>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="rp-card">
          <CardHeader>
            <CardTitle className="text-lg">Send to all admins</CardTitle>
            <CardDescription>Pulls recipients live from the employees table (role = admin).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button onClick={handleSendAll} disabled={sendingAll}>
              {sendingAll ? "Sending\u2026" : "Send to all admins"}
            </Button>
            {sendAllError && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{sendAllError}</p>}
            {sendAllResult && (
              <div className="space-y-2 pt-2">
                <span className={`rp-chip ${wasSent(sendAllResult) ? "rp-chip--up" : "rp-chip--down"}`}>
                  {wasSent(sendAllResult) ? "Accepted by Resend" : "Not sent"}
                </span>
                <pre className="text-xs rounded-md p-3 overflow-x-auto" style={{ background: "var(--rp-canvas)" }}>
                  {JSON.stringify(sendAllResult, null, 2)}
                </pre>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}