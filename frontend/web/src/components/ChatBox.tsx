import { forwardRef, useEffect, useImperativeHandle, useState } from 'react'
import JiraStatus, { type JiraStatusData } from './JiraStatus'
import SprintStatus, { type SprintStatusData } from './SprintStatus'
import UserCard, { type UserCardData } from './UserCard'
import IssueList, { type IssueListData } from './IssueList'
import EtaEstimate, { type EtaEstimateData } from './EtaEstimate'
import SprintSummary, { type SprintSummaryData } from './SprintSummary'
import WorkdaySummary, { type WorkdaySummaryData } from './WorkdaySummary'

type Message = {
  role: 'user' | 'assistant' | 'system'
  content?: string
  ui?:
    | { type: 'jira_status'; data: JiraStatusData }
    | { type: 'sprint_status'; data: SprintStatusData }
    | { type: 'user_card'; data: UserCardData }
    | { type: 'issue_list'; data: IssueListData }
    | { type: 'eta_estimate'; data: EtaEstimateData }
    | { type: 'sprint_summary'; data: SprintSummaryData }
    | { type: 'workday_summary'; data: WorkdaySummaryData }
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

export type ChatBoxHandle = {
  sendContent: (content: string) => Promise<void>
  insertText: (text: string) => void
}

export type ChatUiMessage =
  | { type: 'jira_status'; data: JiraStatusData }
  | { type: 'sprint_status'; data: SprintStatusData }
  | { type: 'user_card'; data: UserCardData }
  | { type: 'issue_list'; data: IssueListData }
  | { type: 'eta_estimate'; data: EtaEstimateData }
  | { type: 'sprint_summary'; data: SprintSummaryData }
  | { type: 'workday_summary'; data: WorkdaySummaryData }

// Helper utilities to extract keys without regex
function extractIssueKey(text: string): string | undefined {
  const candidates: string[] = []
  const parts = (text || '').split(/\s+/)
  for (const raw of parts) {
    // remove leading/trailing punctuation
    const t = raw.replace(/^[-#@()\[\]{}.,:;!?'"`]+|[-#@()\[\]{}.,:;!?'"`]+$/g, '')
    if (!t || t.indexOf('-') === -1) continue
    const [left, right] = t.split('-', 2)
    if (!left || !right) continue
    // left must be uppercase letters/numbers and start with a letter; right must be digits
    const leftOk = (() => {
      if (!/[A-Z]/.test(left[0])) return false
      for (let i = 0; i < left.length; i++) {
        const c = left[i]
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return false
      }
      return true
    })()
    const rightOk = (() => {
      for (let i = 0; i < right.length; i++) {
        const c = right[i]
        if (!(c >= '0' && c <= '9')) return false
      }
      return right.length > 0
    })()
    if (leftOk && rightOk) candidates.push(`${left}-${right}`)
  }
  return candidates[0]
}

function extractProjectKey(text: string): string | undefined {
  // Prefer from issue key if present
  const ik = extractIssueKey(text)
  if (ik && ik.includes('-')) return ik.split('-')[0]
  const parts = (text || '').split(/\s+/)
  for (const raw of parts) {
    const t = raw.replace(/^[-#@()\[\]{}.,:;!?'"`]+|[-#@()\[\]{}.,:;!?'"`]+$/g, '')
    if (!t) continue
    let ok = true
    for (let i = 0; i < t.length; i++) {
      const c = t[i]
      if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) { ok = false; break }
    }
    if (ok && /[A-Z]/.test(t[0])) return t
  }
  return undefined
}

const ChatBox = forwardRef<ChatBoxHandle, { onUiMessage?: (ui: ChatUiMessage) => void }>(function ChatBox(
  { onUiMessage },
  ref,
) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [agentName, setAgentName] = useState('codinator')

  // Fetch and cache Jira base URL for link construction across components
  useEffect(() => {
    const existing = localStorage.getItem('jira_base')
    if (existing) return
    const token = localStorage.getItem('access_token')
    const url = new URL(`${API_BASE}/jira/base-url`)
    fetch(url.toString(), { headers: token ? { Authorization: `Bearer ${token}` } : undefined })
      .then(async (res) => {
        try {
          const data = await res.json()
          if (res.ok && data && typeof data.base === 'string') {
            localStorage.setItem('jira_base', data.base)
          }
        } catch {}
      })
      .catch(() => {})
  }, [])

  // All UI decisions are driven by backend-structured responses.

  const coreSend = async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: Message = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      // Always forward to agent
      const url = new URL(`${API_BASE}/codinator/run-agent`)
      url.searchParams.set('agent_name', agentName)
      // Append lightweight guidance so backend includes total_issues for sprint_summary UI
      const guidance = '\n\n[Frontend requirements]\n- If you return a JSON response with "ui": "sprint_summary", ensure the object has:\n  - Either top-level fields or a nested "data" object.\n  - Include an integer field named "total_issues" in the same nesting level as other fields.\n  - Keep the response format unchanged otherwise.\n';
      const promptText = `${userMsg.content || ''}${guidance}`
      url.searchParams.set('prompt', promptText)
      const token = localStorage.getItem('access_token')
      const res = await fetch(url.toString(), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      const rawBody = await res.text()
      let data: any = null
      try {
        data = JSON.parse(rawBody)
      } catch {
        data = rawBody
      }
      // If it's still a string, try to strip simple code-fences and parse again
      if (typeof data === 'string') {
        let t = data.trim()
        if (t.startsWith('```')) {
          // Drop the first fence line (possibly ```json)
          const firstNl = t.indexOf('\n')
          if (firstNl !== -1) {
            t = t.slice(firstNl + 1)
          }
          // Drop trailing fence if present
          if (t.endsWith('```')) {
            t = t.slice(0, -3)
          }
          t = t.trim()
        }
        try {
          const reparsed = JSON.parse(t)
          if (reparsed && typeof reparsed === 'object') {
            data = reparsed
          }
        } catch {
          // leave as string
        }
      }
      if (!res.ok) {
        const errText = (data && (data.detail || data.error)) || `HTTP ${res.status}`
        throw new Error(errText)
      }
      console.log('Response from /codinator/run-agent:', data);

      // 1) Prefer structured UI directives from backend (ui or type)
      const uiType: string | undefined = (data && (data.ui || data.type)) || undefined

      if (uiType === 'jira_status') {
        const issueKey: string | undefined =
          (typeof (data as any)?.key === 'string' && (data as any).key) ||
          (typeof (data as any)?.issue_key === 'string' && (data as any).issue_key) ||
          (typeof (data as any)?.issueKey === 'string' && (data as any).issueKey) ||
          ((data as any)?.data && typeof (data as any).data.key === 'string' ? (data as any).data.key : undefined) ||
          ((data as any)?.data && typeof (data as any).data.issue_key === 'string' ? (data as any).data.issue_key : undefined) ||
          ((data as any)?.data && typeof (data as any).data.issueKey === 'string' ? (data as any).data.issueKey : undefined) ||
          extractIssueKey(userMsg.content || '')
        console.debug('jira_status detected. Extracted issueKey =', issueKey, 'from payload:', data)
        if (!issueKey) {
          // If no key present, fall back to plain text
          const raw = (data?.data && typeof data.data.text === 'string' ? data.data.text : '') || (typeof data?.response === 'string' ? data.response : '')
          const assistantMsg: Message = { role: 'assistant', content: raw || 'No issue key found.' }
          setMessages((prev) => [...prev, assistantMsg])
          return
        }
        const jurl = new URL(`${API_BASE}/jira/issue-status`)
        jurl.searchParams.set('key', issueKey)
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
          status: jdata.status ?? null,
          comments: Array.isArray(jdata.comments) ? jdata.comments : [],
          url: typeof jdata.url === 'string' ? jdata.url : undefined,
        }
        const ui: ChatUiMessage = { type: 'jira_status', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'sprint_status') {
        const projectKey: string | undefined =
          (typeof (data as any)?.project_key === 'string' && (data as any).project_key) ||
          (typeof (data as any)?.projectKey === 'string' && (data as any).projectKey) ||
          ((data as any)?.data && typeof (data as any).data.project_key === 'string' ? (data as any).data.project_key : undefined) ||
          ((data as any)?.data && typeof (data as any).data.projectKey === 'string' ? (data as any).data.projectKey : undefined) ||
          extractProjectKey(userMsg.content || '')
        console.debug('sprint_status detected. Extracted projectKey =', projectKey, 'from payload:', data)
        if (!projectKey) {
          const raw = (data?.data && typeof data.data.text === 'string' ? data.data.text : '') || (typeof data?.response === 'string' ? data.response : '')
          const assistantMsg: Message = { role: 'assistant', content: raw || 'No project key found.' }
          setMessages((prev) => [...prev, assistantMsg])
          return
        }
        const surl = new URL(`${API_BASE}/jira/sprint-status`)
        surl.searchParams.set('project_key', projectKey)
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
          totalIssues: typeof sdata.totalIssues === 'number' ? sdata.totalIssues : undefined,
          completedIssues: typeof sdata.completedIssues === 'number' ? sdata.completedIssues : undefined,
        }
        const ui: ChatUiMessage = { type: 'sprint_status', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'user_card') {
        // Support both shapes:
        // 1) { ui: 'user_card', name: '...', email: '...', avatarUrl: '...' }
        // 2) { ui: 'user_card', data: { name: '...', email: '...', avatarUrl: '...' } }
        // 3) { type: 'user_card', data: { ... } } (normalized here too)
        const payload = (data.data && typeof data.data === 'object') ? data.data : data
        const uiData: UserCardData = {
          name: String(payload.name || ''),
          designation: typeof payload.designation === 'string' ? payload.designation : undefined,
          email: typeof payload.email === 'string' ? payload.email : undefined,
          avatarUrl: typeof payload.avatarUrl === 'string' ? payload.avatarUrl : undefined,
          online: typeof payload.online === 'boolean' ? payload.online : undefined,
        }
        if (!uiData.name) {
          // If name is missing, fall back to plain text rendering below
          const assistantMsg: Message = { role: 'assistant', content: 'No assignee information available.' }
          setMessages((prev) => [...prev, assistantMsg])
          return
        }
        const ui: ChatUiMessage = { type: 'user_card', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'issue_list') {
        // Support both shapes:
        // 1) { ui: 'issue_list', issues: [...], title? }
        // 2) { ui: 'issue_list', data: { issues: [...], title? } }
        const payload = Array.isArray(data.issues)
          ? { title: data.title, issues: data.issues }
          : (data.data || {})

        const issuesArr = Array.isArray(payload.issues) ? payload.issues : []

        const uiData: IssueListData = {
          title: typeof payload.title === 'string' ? payload.title : undefined,
          issues: issuesArr
            .map((it: any) => ({
              key: String(it.key || ''),
              summary: typeof it.summary === 'string' ? it.summary : undefined,
              status: typeof it.status === 'string' ? it.status : undefined,
              priority: typeof it.priority === 'string' ? it.priority : undefined,
              url: typeof it.url === 'string' ? it.url : undefined,
            }))
            .filter((it: any) => it.key),
        }
        const ui: ChatUiMessage = { type: 'issue_list', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'eta_estimate') {
        // Expect either { ui: 'eta_estimate', issue_key } or nested under data.issue_key
        const issueKey: string | undefined =
          (typeof (data as any)?.issue_key === 'string' && (data as any).issue_key) ||
          (typeof (data as any)?.issueKey === 'string' && (data as any).issueKey) ||
          ((data as any)?.data && typeof (data as any).data.issue_key === 'string' ? (data as any).data.issue_key : undefined) ||
          ((data as any)?.data && typeof (data as any).data.issueKey === 'string' ? (data as any).data.issueKey : undefined) ||
          extractIssueKey(userMsg.content || '')
        if (!issueKey) {
          const assistantMsg: Message = { role: 'assistant', content: 'No issue key found for ETA request.' }
          setMessages((prev) => [...prev, assistantMsg])
          return
        }
        const eurl = new URL(`${API_BASE}/jira/issue-eta-graph`)
        eurl.searchParams.set('issue_key', issueKey)
        const token = localStorage.getItem('access_token')
        const eres = await fetch(eurl.toString(), {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        })
        let edata: any = null
        try { edata = await eres.json() } catch {}
        if (!eres.ok) {
          const errText = edata?.detail || edata?.error || `HTTP ${eres.status}`
          throw new Error(errText)
        }
        // Normalize backend payload to EtaEstimateData
        const uiData: EtaEstimateData = {
          issue: String(edata.issue || issueKey),
          project_key: String(edata.project_key || issueKey.split('-')[0] || ''),
          optimistic_days: typeof edata.optimistic_days === 'number' ? edata.optimistic_days : 0,
          pessimistic_days: typeof edata.pessimistic_days === 'number' ? edata.pessimistic_days : (typeof edata.optimistic_days === 'number' ? edata.optimistic_days : 0),
          optimistic_critical_path: Array.isArray(edata.optimistic_critical_path) ? edata.optimistic_critical_path : [],
          pessimistic_blockers: Array.isArray(edata.pessimistic_blockers) ? edata.pessimistic_blockers : [],
          nodes: (edata.nodes && typeof edata.nodes === 'object') ? edata.nodes : {},
          summary: typeof edata.summary === 'string' ? edata.summary : undefined,
        }
        const ui: ChatUiMessage = { type: 'eta_estimate', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'sprint_summary') {
        // Support both shapes:
        // 1) { ui: 'sprint_summary', project, total_issues, status_counts, sample_issues }
        // 2) { ui: 'sprint_summary', data: { ... } }
        const payload = (data && typeof data.data === 'object') ? data.data : data
        const rawIssues = Array.isArray(payload.sample_issues) ? payload.sample_issues : []
        const uiData: SprintSummaryData = {
          project: typeof payload.project === 'string' ? payload.project : '',
          total_issues: typeof payload.total_issues === 'number' ? payload.total_issues : 0,
          status_categories: (payload.status_categories && typeof payload.status_categories === 'object')
            ? payload.status_categories
            : ((payload.status_counts && typeof payload.status_counts === 'object') ? payload.status_counts : {}),
          sample_issues: rawIssues
            .map((it: any) => ({
              key: String(it.key || ''),
              summary: typeof it.summary === 'string' ? it.summary : undefined,
              status: typeof it.status === 'string' ? it.status : undefined,
              priority: typeof it.priority === 'string' ? it.priority : undefined,
              url: typeof it.url === 'string' ? it.url : undefined,
            }))
            .filter((it: any) => it.key),
          sprintName: typeof payload.sprintName === 'string'
            ? payload.sprintName
            : (typeof payload.status === 'string' ? payload.status : undefined),
          startDate: typeof payload.startDate === 'string'
            ? payload.startDate
            : (typeof payload.start === 'string' ? payload.start : undefined),
          endDate: typeof payload.endDate === 'string'
            ? payload.endDate
            : (typeof payload.end === 'string' ? payload.end : undefined),
        }
        const ui: ChatUiMessage = { type: 'sprint_summary', data: uiData }
        const uiMsg: Message = { role: 'assistant', ui }
        setMessages((prev) => [...prev, uiMsg])
        onUiMessage?.(ui)
      } else if (uiType === 'generic') {
        // Generic directive – show provided text
        const raw = (data?.data && typeof data.data.text === 'string' ? data.data.text : '') || (typeof data?.response === 'string' ? data.response : '')
        const assistantMsg: Message = { role: 'assistant', content: raw || 'No response from agent' }
        setMessages((prev) => [...prev, assistantMsg])
      } else if (uiType) {
        // Unknown UI type – show best-effort text
        const raw = (data?.data && typeof data.data.text === 'string' ? data.data.text : '') || (typeof data?.response === 'string' ? data.response : '')
        const assistantMsg: Message = { role: 'assistant', content: raw || `[${uiType}]` }
        setMessages((prev) => [...prev, assistantMsg])
      } else if (true) {
        // Plain text fallback – try to render structured UI for start/end day commands
        const raw = (data?.response && String(data.response).trim()) || ''
        const original = userMsg.content || ''
        const norm = original.toLowerCase().split(/\s+/).join(' ').trim()

        const parseStart = (t: string): WorkdaySummaryData | null => {
          const lines = (t || '').split('\n').map((s) => s.trim())
          if (lines.length === 0) return null
          const out: WorkdaySummaryData = { mode: 'start', title: 'Workday started' }
          for (let i = 0; i < lines.length; i++) {
            const line = lines[i]
            if (line.startsWith('Workday started at ')) {
              out.startedAt = line.slice('Workday started at '.length)
            } else if (line.startsWith('Tracking GitHub ')) {
              const rest = line.slice('Tracking GitHub '.length)
              // rest can be e.g. "owner/repo@branch." or "owner/repo (default branch)."
              let clean = rest
              if (clean.endsWith('.')) clean = clean.slice(0, -1)
              const atIdx = clean.indexOf('@')
              if (atIdx !== -1) {
                out.trackingRepo = clean.slice(0, atIdx)
                out.trackingBranch = clean.slice(atIdx + 1)
              } else {
                const sp = clean.indexOf(' ')
                out.trackingRepo = sp === -1 ? clean : clean.slice(0, sp)
              }
            } else if (line === "- Due today:") {
              const issues: { key: string; summary?: string; due?: string }[] = []
              let j = i + 1
              while (j < lines.length) {
                const l = lines[j]
                if (!l.startsWith('•') && !l.startsWith('-') && !l.startsWith('  •')) break
                const s = l.replace(/^[-•]\s*/,'').replace(/^\u2022\s*/, '').trim()
                if (s && s !== 'None' && s.indexOf(':') !== -1) {
                  const colon = s.indexOf(':')
                  const key = s.slice(0, colon).trim()
                  let rest = s.slice(colon + 1).trim()
                  // extract due in parens at end if present
                  let due: string | undefined
                  if (rest.endsWith(')')) {
                    const open = rest.lastIndexOf('(')
                    if (open !== -1 && open < rest.length - 1) {
                      due = rest.slice(open + 1, rest.length - 1)
                      rest = rest.slice(0, open).trim()
                    }
                  }
                  issues.push({ key, summary: rest, due })
                }
                j++
              }
              out.dueToday = issues
            } else if (line === "- In progress / next up:") {
              const issues: { key: string; summary?: string; status?: string }[] = []
              let j = i + 1
              while (j < lines.length) {
                const l = lines[j]
                if (!l.startsWith('•') && !l.startsWith('-') && !l.startsWith('  •')) break
                const s = l.replace(/^[-•]\s*/,'').replace(/^\u2022\s*/, '').trim()
                if (s && s !== 'None') {
                  // Expected: KEY: summary [STATUS]
                  const colon = s.indexOf(':')
                  if (colon !== -1) {
                    const key = s.slice(0, colon).trim()
                    let rest = s.slice(colon + 1).trim()
                    let status: string | undefined
                    if (rest.endsWith(']')) {
                      const open = rest.lastIndexOf('[')
                      if (open !== -1 && open < rest.length - 1) {
                        status = rest.slice(open + 1, rest.length - 1)
                        rest = rest.slice(0, open).trim()
                      }
                    }
                    issues.push({ key, summary: rest, status })
                  }
                }
                j++
              }
              out.nextUp = issues
            }
          }
          return out
        }

        const parseEnd = (t: string): WorkdaySummaryData | null => {
          const lines = (t || '').split('\n').map((s) => s.trim())
          if (!lines.length) return null
          const out: WorkdaySummaryData = { mode: 'end', title: 'Workday summary' }
          for (let i = 0; i < lines.length; i++) {
            const line = lines[i]
            if (line.startsWith('Workday summary since ')) {
              out.since = line.slice('Workday summary since '.length)
            } else if (line === 'Jira:' && i + 3 < lines.length) {
              const c = lines[i + 1]
              const r = lines[i + 2]
              const w = lines[i + 3]
              const numOrStr = (s: string, prefix: string): number | string | undefined => {
                if (!s.startsWith(prefix)) return undefined
                const v = s.slice(prefix.length).trim()
                const n = Number(v)
                return Number.isFinite(n) ? n : v
              }
              out.jira = {
                completed: numOrStr(c, '- Completed issues: '),
                raised: numOrStr(r, '- Raised issues: '),
                working: numOrStr(w, '- Working on: '),
              }
            } else if (line === 'GitHub commits:') {
              const gh: { repo?: string; summaryText?: string } = {}
              // Next line might be Repository: ...
              let j = i + 1
              if (j < lines.length && lines[j].startsWith('Repository: ')) {
                gh.repo = lines[j].slice('Repository: '.length)
                j++
              }
              gh.summaryText = lines.slice(j).join('\n')
              out.github = gh
              break
            }
          }
          return out
        }

        let uiData: WorkdaySummaryData | null = null
        if (norm.includes('--start day') || norm.includes('--start-day')) {
          uiData = parseStart(raw)
        } else if (norm.includes('--end day') || norm.includes('--end-day')) {
          uiData = parseEnd(raw)
        }

        if (uiData) {
          const ui: ChatUiMessage = { type: 'workday_summary', data: uiData }
          const uiMsg: Message = { role: 'assistant', ui }
          setMessages((prev) => [...prev, uiMsg])
          onUiMessage?.(ui)
        } else {
          const assistantMsg: Message = {
            role: 'assistant',
            content: raw || 'No response from agent'
          }
          setMessages((prev) => [...prev, assistantMsg])
        }
      }
    }
    catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'system', content: `Error: ${e?.message || 'Unknown error'}` },
      ])
    }
    finally {
      setLoading(false)
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const current = input
    setInput('')
    await coreSend(current)
  }

  useImperativeHandle(ref, () => ({
    sendContent: async (content: string) => {
      await coreSend(content)
    },
    insertText: (text: string) => {
      const t = (text || '').trim()
      if (!t) return
      setInput((prev) => (prev && prev.trim().length > 0 ? `${prev} ${t}` : t))
    },
  }))

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex-grow flex flex-col bg-secondary-800 border border-secondary-600"> {/* Adjusted styling */}
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
            className={`p-2 rounded-lg whitespace-pre-wrap break-words leading-tight text-sm animate-fadeIn ${
              m.ui ? 'w-full max-w-[900px] md:max-w-[1100px]' : 'max-w-[700px]'
            } ${
              m.role === 'user'
                ? `bg-secondary-700 ${m.ui ? 'self-center' : 'self-end'}`
                : m.role === 'assistant'
                ? `bg-secondary-900 ${m.ui ? 'self-center' : 'self-start'} border border-secondary-700`
                : 'bg-red-900 self-center'
            }`}
          >
            {m.ui?.type === 'jira_status' ? (
              <JiraStatus data={m.ui.data} />
            ) : m.ui?.type === 'sprint_status' ? (
              <SprintStatus data={m.ui.data} />
            ) : m.ui?.type === 'user_card' ? (
              <UserCard data={m.ui.data} />
            ) : m.ui?.type === 'issue_list' ? (
              <IssueList data={m.ui.data} />
            ) : m.ui?.type === 'eta_estimate' ? (
              <EtaEstimate data={m.ui.data} />
            ) : m.ui?.type === 'sprint_summary' ? (
              <SprintSummary data={m.ui.data} />
            ) : m.ui?.type === 'workday_summary' ? (
              <WorkdaySummary data={m.ui.data} />
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
})

export default ChatBox
