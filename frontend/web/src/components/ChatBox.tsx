import { useState } from 'react'
import JiraStatus, { type JiraStatusData } from './JiraStatus'
import SprintStatus, { type SprintStatusData } from './SprintStatus'

type Message = {
  role: 'user' | 'assistant' | 'system'
  content?: string
  ui?:
    | { type: 'jira_status'; data: JiraStatusData }
    | { type: 'sprint_status'; data: SprintStatusData }
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

export default function ChatBox() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [agentName, setAgentName] = useState('codinator')

  // Try to parse a UI directive from raw model text.
  // Supports plain JSON, ```json fenced blocks, ``` fenced blocks, and inline objects.
  const parseDirective = (raw: string): any | null => {
    if (!raw) return null
    // 1) direct JSON
    try { return JSON.parse(raw) } catch {}
    // 2) code-fenced ```json ... ```
    const fenceJson = /```json\s*([\s\S]*?)\s*```/i.exec(raw)
    if (fenceJson && fenceJson[1]) {
      const inner = fenceJson[1].trim()
      try { return JSON.parse(inner) } catch {}
    }
    // 3) generic code fence ``` ... ```
    const fence = /```\s*([\s\S]*?)\s*```/i.exec(raw)
    if (fence && fence[1]) {
      const inner = fence[1].trim()
      try { return JSON.parse(inner) } catch {}
    }
    // 4) inline minimal match for our directive
    const inline = /\{\s*"ui"\s*:\s*"jira_status"[\s\S]*?\}/i.exec(raw)
    if (inline && inline[0]) {
      try { return JSON.parse(inline[0]) } catch {}
    }
    // 5) inline minimal match for sprint directive
    const inlineSprint = /\{\s*"ui"\s*:\s*"sprint_status"[\s\S]*?\}/i.exec(raw)
    if (inlineSprint && inlineSprint[0]) {
      try { return JSON.parse(inlineSprint[0]) } catch {}
    }
    return null
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      // Always forward to agent
      const url = new URL(`${API_BASE}/codinator/run-agent`)
      url.searchParams.set('agent_name', agentName)
      url.searchParams.set('prompt', userMsg.content || '')
      const token = localStorage.getItem('access_token')
      const res = await fetch(url.toString(), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      let data: any = null
      try { data = await res.json() } catch {}
      if (!res.ok) {
        const errText = data?.detail || data?.error || `HTTP ${res.status}`
        throw new Error(errText)
      }
      const raw = (data?.response && String(data.response).trim()) || ''

      // Try to parse a structured UI directive (supports code fences)
      const parsed: any = parseDirective(raw)

      if (parsed && parsed.ui === 'jira_status' && typeof parsed.key === 'string') {
        const jurl = new URL(`${API_BASE}/jira/issue-status`)
        jurl.searchParams.set('key', parsed.key)
        const token = localStorage.getItem('access_token')
        const jres = await fetch(jurl.toString(), {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        })
        let jdata: any = null
        try { jdata = await jres.json() } catch {}
        if (!jres.ok) {
          const errText = jdata?.detail || jdata?.error || `HTTP ${jres.status}`
          throw new Error(errText)
        }
        const uiData: JiraStatusData = {
          key: jdata.key,
          name: jdata.name ?? null,
          expectedFinishDate: jdata.expectedFinishDate ?? null,
          comments: Array.isArray(jdata.comments) ? jdata.comments : [],
        }
        const uiMsg: Message = { role: 'assistant', ui: { type: 'jira_status', data: uiData } }
        setMessages((prev) => [...prev, uiMsg])
      } else if (parsed && parsed.ui === 'sprint_status' && typeof parsed.project_key === 'string') {
        const surl = new URL(`${API_BASE}/jira/sprint-status`)
        surl.searchParams.set('project_key', parsed.project_key)
        const token = localStorage.getItem('access_token')
        const sres = await fetch(surl.toString(), {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        })
        let sdata: any = null
        try { sdata = await sres.json() } catch {}
        if (!sres.ok) {
          const errText = sdata?.detail || sdata?.error || `HTTP ${sres.status}`
          throw new Error(errText)
        }
        const uiData: SprintStatusData = {
          name: sdata.name ?? null,
          startDate: sdata.startDate ?? null,
          endDate: sdata.endDate ?? null,
          notes: Array.isArray(sdata.notes) ? sdata.notes : [],
        }
        const uiMsg: Message = { role: 'assistant', ui: { type: 'sprint_status', data: uiData } }
        setMessages((prev) => [...prev, uiMsg])
      } else {
        const assistantMsg: Message = {
          role: 'assistant',
          content: raw || 'No response from agent'
        }
        setMessages((prev) => [...prev, assistantMsg])
      }
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'system', content: `Error: ${e?.message || 'Unknown error'}` },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="fixed top-4 right-4 w-80 h-[80vh] flex flex-col bg-secondary-800 border border-secondary-600 rounded-xl overflow-hidden shadow-xl z-50">
      <div className="flex items-center justify-between p-3 border-b border-secondary-600">
        <div className="text-sm opacity-90">Chat</div>
        <select
          className="bg-secondary-900 text-white border border-secondary-600 rounded-lg px-2 py-1 text-xs"
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
        >
          <option value="codinator">codinator</option>
        </select>
      </div>

      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`p-2 rounded-lg max-w-[85%] whitespace-pre-wrap break-words leading-tight text-sm ${
              m.role === 'user' ? 'bg-secondary-700 self-end' : m.role === 'assistant' ? 'bg-secondary-900 self-start border border-secondary-700' : 'bg-red-900 self-center'
            }`}
          >
            {m.ui?.type === 'jira_status' ? (
              <JiraStatus data={m.ui.data} />
            ) : m.ui?.type === 'sprint_status' ? (
              <SprintStatus data={m.ui.data} />
            ) : (
              m.content
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-2 p-3 border-t border-secondary-600 bg-secondary-900">
        <input
          className="flex-1 px-3 py-2 rounded-lg border border-secondary-600 bg-secondary-900 text-white"
          type="text"
          placeholder={loading ? 'Waiting for response…' : 'Type a message and press Enter'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className={`px-3 py-2 rounded-lg border border-secondary-600 text-white ${
            loading ? 'bg-secondary-700 cursor-not-allowed' : 'bg-primary-600 cursor-pointer'
          }`}
          onClick={sendMessage}
          disabled={loading}
        >
          Send
        </button>
      </div>
    </div>
  )
}
