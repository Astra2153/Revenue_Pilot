import { useState } from "react"
import { adminLogin } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/** Short, readable description of the browser/OS, for the access log. */
function describeDevice(): string {
  const ua = navigator.userAgent
  const browser =
    /Edg\//.test(ua) ? "Edge" :
    /Chrome\//.test(ua) && !/Edg\//.test(ua) ? "Chrome" :
    /Firefox\//.test(ua) ? "Firefox" :
    /Safari\//.test(ua) && !/Chrome\//.test(ua) ? "Safari" :
    "Unknown browser"
  const os =
    /Windows/.test(ua) ? "Windows" :
    /Android/.test(ua) ? "Android" :
    /iPhone|iPad/.test(ua) ? "iOS" :
    /Mac OS X/.test(ua) ? "macOS" :
    /Linux/.test(ua) ? "Linux" :
    "Unknown OS"
  return `${browser} on ${os}`
}

interface AdminLoginGateProps {
  onUnlock: () => void
}

export default function AdminLoginGate({ onUnlock }: AdminLoginGateProps) {
  const [passkey, setPasskey] = useState("")
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hintShown, setHintShown] = useState(false)

  async function handleSubmit() {
    if (!passkey || checking) return
    setChecking(true)
    setError(null)
    try {
      await adminLogin(passkey, describeDevice())
      onUnlock()
    } catch {
      // The backend returns 401 with its own message; keep the surfaced
      // copy short and actionable rather than echoing a raw HTTP error.
      setError("That passkey didn't match. Try again.")
      setPasskey("")
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="p-8 flex justify-center">
      <Card className="w-full max-w-md mt-12">
        <CardHeader>
          <p className="rp-eyebrow mb-1">Restricted</p>
          <CardTitle className="text-2xl">Admin Portal</CardTitle>
          <CardDescription>
            Managing employees and viewing access history needs the admin passkey.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="passkey">Passkey</Label>
            <Input
              id="passkey"
              type="password"
              autoFocus
              value={passkey}
              onChange={(e) => setPasskey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="Enter passkey"
              disabled={checking}
            />
          </div>

          {error && <p className="text-sm" style={{ color: "var(--rp-signal)" }}>{error}</p>}

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setHintShown(true)}
              className="text-xs underline underline-offset-2"
              style={{ color: "var(--rp-slate)" }}
            >
              Forgot the passkey?
            </button>
            <Button onClick={handleSubmit} disabled={checking || !passkey}>
              {checking ? "Checking\u2026" : "Unlock"}
            </Button>
          </div>

          {hintShown && (
            <p
              className="text-sm rounded-md p-3"
              style={{ background: "var(--rp-blush)", color: "var(--rp-ink)" }}
            >
              Hint: 1, 2, 3, 4
            </p>
          )}

          <p className="text-xs pt-2" style={{ color: "var(--rp-slate)" }}>
            The passkey is checked on the server, and every attempt is recorded in the access log below
            once you're in.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}