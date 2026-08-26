import { useState, useRef, useEffect } from "react"
import { sendChatMessage, askQuery, type NLQueryResponse } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const ALL_MODULES = "all"
const MODULES = [
  { value: ALL_MODULES, label: "All Modules" },
  { value: "sales", label: "Sales" },
  { value: "marketing", label: "Marketing" },
  { value: "finance", label: "Finance" },
  { value: "customer", label: "Customer" },
]

const DIVISIONS = [
  { value: "admin", label: "Admin (all tables)" },
  { value: "sales", label: "Sales" },
  { value: "marketing", label: "Marketing" },
  { value: "finance", label: "Finance" },
  { value: "customer", label: "Customer" },
]

interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

function AskAIPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [module, setModule] = useState(ALL_MODULES)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, sending])

  async function handleSend() {
    const trimmed = input.trim()
    if (!trimmed || sending) return

    setMessages((prev) => [...prev, { role: "user", content: trimmed }])
    setInput("")
    setSending(true)
    setError(null)

    try {
      const result = await sendChatMessage(trimmed, module === ALL_MODULES ? null : module)
      setMessages((prev) => [...prev, { role: "assistant", content: result.response }])
    } catch (err) {
      setError(String(err))
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSend()
  }

  return (
    <Card className="flex-1 flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Ask AI</CardTitle>
            <CardDescription>
              Conversational answers grounded in pre-computed analytics summaries -- ask about trends,
              comparisons, or "why" something happened.
            </CardDescription>
          </div>
          <Select value={module} onValueChange={setModule}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODULES.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4 overflow-hidden">
        <div className="flex-1 overflow-y-auto space-y-3 min-h-64 max-h-[45vh] border rounded-lg p-4 bg-gray-50">
          {messages.length === 0 && (
            <p className="text-gray-400 text-sm">No messages yet -- ask something below.</p>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                  msg.role === "user" ? "bg-blue-600 text-white" : "bg-white border text-gray-900"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-white border rounded-lg px-4 py-2 text-sm text-gray-400">Thinking...</div>
            </div>
          )}
          <div ref={scrollRef} />
        </div>
        {error && <p className="text-red-600 text-sm">Error: {error}</p>}
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data..."
            disabled={sending}
          />
          <Button onClick={handleSend} disabled={sending || !input.trim()}>
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function QueryDataPanel() {
  const [division, setDivision] = useState("admin")
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState<NLQueryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    const trimmed = question.trim()
    if (!trimmed || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await askQuery(trimmed, division)
      setResult(res)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSubmit()
  }

  const columns = result?.rows && result.rows.length > 0 ? Object.keys(result.rows[0]) : []

  return (
    <Card className="flex-1 flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Query Data</CardTitle>
            <CardDescription>
              Ask in plain English -- an AI writes real SQL, which is validated (read-only, no
              cross-division access, no forbidden tables) before it ever runs. You always see the
              exact SQL that executed.
            </CardDescription>
          </div>
          <Select value={division} onValueChange={setDivision}>
            <SelectTrigger className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DIVISIONS.map((d) => (
                <SelectItem key={d.value} value={d.value}>
                  {d.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4">
        <div className="flex gap-2">
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. What were total sales by region last month?"
            disabled={loading}
          />
          <Button onClick={handleSubmit} disabled={loading || !question.trim()}>
            {loading ? "Running..." : "Run Query"}
          </Button>
        </div>

        {error && <p className="text-red-600 text-sm">Error: {error}</p>}

        {result && (
          <div className="space-y-4 overflow-y-auto max-h-[50vh]">
            <div className="flex items-center gap-2">
              <Badge
                variant={
                  result.status === "ok" ? "default" : result.status === "refused" ? "secondary" : "destructive"
                }
              >
                {result.status}
              </Badge>
              {result.row_count !== undefined && (
                <span className="text-sm text-gray-500">
                  {result.row_count} row{result.row_count !== 1 ? "s" : ""}
                  {result.truncated ? " (truncated)" : ""}
                </span>
              )}
            </div>

            {result.status === "refused" && (
              <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">
                {result.reason}
              </p>
            )}
            {result.status === "error" && (
              <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">{result.error}</p>
            )}

            {result.generated_sql && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Generated SQL (read-only, validated before running):</p>
                <pre className="text-xs bg-gray-900 text-gray-100 rounded p-3 overflow-x-auto">
                  {result.generated_sql}
                </pre>
              </div>
            )}

            {result.answer && <p className="text-sm">{result.answer}</p>}

            {result.rows && result.rows.length > 0 && (
              <div className="overflow-x-auto border rounded">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columns.map((col) => (
                        <TableHead key={col}>{col}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.rows.map((row, i) => (
                      <TableRow key={i}>
                        {columns.map((col) => (
                          <TableCell key={col} className="text-sm">
                            {String(row[col] ?? "--")}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function Chatbot() {
  return (
    <div className="p-8 space-y-4 h-full flex flex-col">
      <h1 className="text-3xl font-bold">Chatbot</h1>
      <Tabs defaultValue="ask-ai" className="flex-1 flex flex-col">
        <TabsList>
          <TabsTrigger value="ask-ai">Ask AI</TabsTrigger>
          <TabsTrigger value="query-data">Query Data</TabsTrigger>
        </TabsList>
        <TabsContent value="ask-ai" className="flex-1 flex flex-col">
          <AskAIPanel />
        </TabsContent>
        <TabsContent value="query-data" className="flex-1 flex flex-col">
          <QueryDataPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}