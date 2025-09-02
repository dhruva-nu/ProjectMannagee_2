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
      const res = await fetch(url.toString(), { method: 'POST' })
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
        const jres = await fetch(jurl.toString())
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
        const sres = await fetch(surl.toString())
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

  // Simple right-fixed chat UI
  const styles: Record<string, React.CSSProperties> = {
    wrapper: {
      position: 'fixed',
      top: 16,
      right: 16,
      width: 340,
      height: '80vh',
      display: 'flex',
      flexDirection: 'column',
      background: '#1a1a1a',
      border: '1px solid #333',
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
      zIndex: 1000,
    },
    header: {
      padding: '10px 12px',
      borderBottom: '1px solid #333',
      display: 'flex',
      gap: 8,
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    title: { fontSize: 14, opacity: 0.9 },
    select: {
      background: '#0f0f0f',
      color: '#fff',
      border: '1px solid #333',
      borderRadius: 8,
      padding: '6px 8px',
      fontSize: 12,
    },
    messages: {
      flex: 1,
      overflowY: 'auto',
      padding: 12,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    },
    msg: {
      padding: '8px 10px',
      borderRadius: 8,
      maxWidth: '85%',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      lineHeight: 1.35,
      fontSize: 13,
    },
    user: { background: '#2a2a2a', alignSelf: 'flex-end' },
    assistant: { background: '#111', alignSelf: 'flex-start', border: '1px solid #262626' },
    system: { background: '#3a1f1f', alignSelf: 'center' },
    inputBar: {
      display: 'flex',
      gap: 8,
      padding: 12,
      borderTop: '1px solid #333',
      background: '#141414',
    },
    input: {
      flex: 1,
      padding: '10px 12px',
      borderRadius: 10,
      border: '1px solid #333',
      background: '#0f0f0f',
      color: '#fff',
    },
    button: {
      padding: '10px 12px',
      borderRadius: 10,
      border: '1px solid #333',
      background: loading ? '#2b2b2b' : '#1f6feb',
      color: '#fff',
      cursor: loading ? 'not-allowed' as const : 'pointer',
    },
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <div style={styles.title}>Chat</div>
        <select
          style={styles.select}
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
        >
          <option value="codinator">codinator</option>
        </select>
      </div>

      <div style={styles.messages}>
        {messages.map((m, idx) => (
          <div
            key={idx}
            style={{
              ...styles.msg,
              ...(m.role === 'user' ? styles.user : m.role === 'assistant' ? styles.assistant : styles.system),
            }}
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

      <div style={styles.inputBar}>
        <input
          style={styles.input}
          type="text"
          placeholder={loading ? 'Waiting for response…' : 'Type a message and press Enter'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button style={styles.button} onClick={sendMessage} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  )
}
