import { Routes, Route } from "react-router-dom"
import Layout from "@/components/Layout"
import Dashboard from "@/pages/Dashboard"
import CRMPortal from "@/pages/CRMPortal"
import AdminPortal from "@/pages/AdminPortal"
import MarketingFunnel from "@/pages/MarketingFunnel"
import ScenarioSimulator from "@/pages/ScenarioSimulator"
import Chatbot from "@/pages/Chatbot"
import AuditLog from "@/pages/AuditLog"

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/crm" element={<CRMPortal />} />
        <Route path="/admin" element={<AdminPortal />} />
        <Route path="/marketing" element={<MarketingFunnel />} />
        <Route path="/simulator" element={<ScenarioSimulator />} />
        <Route path="/chatbot" element={<Chatbot />} />
        <Route path="/audit-log" element={<AuditLog />} />
      </Route>
    </Routes>
  )
}

export default App