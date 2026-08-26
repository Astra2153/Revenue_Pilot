import { Link, Outlet, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
import logo from "@/assets/revenuepilot-logo.svg"

const NAV_ITEMS = [
  { path: "/", label: "Dashboard" },
  { path: "/crm", label: "CRM" },
  { path: "/admin", label: "Admin" },
  { path: "/marketing", label: "Marketing Funnel" },
  { path: "/simulator", label: "Scenario Simulator" },
  { path: "/chatbot", label: "Chatbot" },
  { path: "/audit-log", label: "Audit Log" },
]

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export default function Layout() {
  const location = useLocation()

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 border-r bg-white p-4 flex flex-col">
        <img src={logo} alt="RevenuePilot" className="w-full h-auto mb-4 px-1" />
        <div className="space-y-1 flex-1">
          {NAV_ITEMS.map((item) => (
            <Link key={item.path} to={item.path} className={cn("block rounded px-3 py-2 text-sm font-medium hover:bg-gray-100", location.pathname === item.path && "bg-gray-100 text-blue-600")}>
              {item.label}
            </Link>
          ))}
        </div>
        <a href={API_BASE_URL + "/docs"} target="_blank" rel="noopener noreferrer" className="block rounded px-3 py-2 text-sm font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-900 border-t pt-4 mt-2">
          Backend API Docs
        </a>
      </aside>
      <main className="flex-1 bg-gray-50">
        <Outlet />
      </main>
    </div>
  )
}