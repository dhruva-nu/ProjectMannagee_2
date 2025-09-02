import { useState } from 'react'

type Message = {
  role: 'user' | 'assistant' | 'system'
  content: string
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

export default function ChatBox() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [agentName, setAgentName] = useState('codinator')

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const url = new URL(`${API_BASE}/codinator/run-agent`)
      url.searchParams.set('agent_name', agentName)
      url.searchParams.set('prompt', userMsg.content)

      const res = await fetch(url.toString(), { method: 'POST' })
      let data: any = null
      try { data = await res.json() } catch {}
      if (!res.ok) {
        const errText = data?.detail || data?.error || `HTTP ${res.status}`
        throw new Error(errText)
      }
      const assistantMsg: Message = {
        role: 'assistant',
        content: (data?.response && String(data.response).trim()) || 'No response from agent'
      }
      setMessages((prev) => [...prev, assistantMsg])
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
            {m.content}
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
