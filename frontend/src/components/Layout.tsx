import { useEffect, useState } from "react"
import { Link, Outlet, useLocation } from "react-router-dom"
import {
  LayoutDashboard,
  Landmark,
  Megaphone,
  Users,
  SlidersHorizontal,
  Briefcase,
  Shield,
  MessageSquare,
  ScrollText,
  Mail,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { getHealth } from "@/lib/api"
import logo from "@/assets/revenuepilot-logo.svg"

/* Grouped by what each page is FOR, not alphabetically -- the headings
   carry real information about the shape of the app. */
const NAV_GROUPS = [
  {
    heading: "Overview",
    items: [{ path: "/", label: "Dashboard", Icon: LayoutDashboard }],
  },
  {
    heading: "Analytics",
    items: [
      { path: "/finance", label: "Finance", Icon: Landmark },
      { path: "/marketing", label: "Marketing", Icon: Megaphone },
      { path: "/customer-intelligence", label: "Customers", Icon: Users },
      { path: "/simulator", label: "Simulator", Icon: SlidersHorizontal },
    ],
  },
  {
    heading: "Operations",
    items: [
      { path: "/crm", label: "CRM", Icon: Briefcase },
      { path: "/admin", label: "Admin", Icon: Shield },
    ],
  },
  {
    heading: "Tools",
    items: [
      { path: "/chatbot", label: "Chatbot", Icon: MessageSquare },
      { path: "/reports", label: "Reports", Icon: Mail },
      { path: "/audit-log", label: "Audit Log", Icon: ScrollText },
    ],
  },
]

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

type ApiState = "waking" | "live" | "down"

const LAMP_COPY: Record<ApiState, string> = {
  waking: "Connecting\u2026",
  live: "API connected",
  down: "API unreachable",
}

export default function Layout() {
  const location = useLocation()
  const [apiState, setApiState] = useState<ApiState>("waking")

  useEffect(() => {
    let cancelled = false
    const check = () => {
      getHealth()
        .then(() => !cancelled && setApiState("live"))
        .catch(() => !cancelled && setApiState("down"))
    }
    check()
    const timer = setInterval(check, 60000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="flex min-h-screen">
      <aside className="rp-sidebar w-60 shrink-0 flex flex-col p-3">
        <img src={logo} alt="RevenuePilot" className="w-full h-auto mb-6 mt-2 px-2" />

        <nav className="flex-1 overflow-y-auto space-y-5">
          {NAV_GROUPS.map((group) => (
            <div key={group.heading}>
              <p className="rp-eyebrow px-3 mb-1.5">{group.heading}</p>
              <div className="space-y-0.5">
                {group.items.map(({ path, label, Icon }) => (
                  <Link
                    key={path}
                    to={path}
                    className={cn("rp-navitem", location.pathname === path && "rp-navitem--active")}
                  >
                    <Icon className="rp-navicon" size={17} strokeWidth={2} />
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-4 pt-3 px-1" style={{ borderTop: "1px solid var(--rp-hairline)" }}>
          <div className="flex items-center gap-2 px-2 mb-1.5">
            <span className={cn("rp-lamp", `rp-lamp--${apiState}`)} aria-hidden="true" />
            <span className="text-xs" style={{ color: "var(--rp-slate)" }}>
              {LAMP_COPY[apiState]}
            </span>
          </div>
          <a
            href={API_BASE_URL + "/docs"}
            target="_blank"
            rel="noopener noreferrer"
            className="block rounded-lg px-2 py-1.5 text-xs font-medium hover:bg-white/70"
            style={{ color: "var(--rp-slate)" }}
          >
            Backend API docs
          </a>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  )
}
