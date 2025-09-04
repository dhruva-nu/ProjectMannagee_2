import { useEffect, useState } from 'react'

export type IssueListItem = {
  key: string
  summary?: string
  status?: string
  priority?: string
  url?: string
}

export type IssueListData = {
  title?: string
  issues: IssueListItem[]
}

export default function IssueList({ data }: { data: IssueListData }) {
  const { title = 'Issues', issues } = data
  const [animate, setAnimate] = useState(false)

  useEffect(() => {
    setAnimate(false)
    void document.getElementById('issue-list-card')?.offsetWidth
    setAnimate(true)
  }, [JSON.stringify(issues), title])

  return (
    <div id="issue-list-card" className={`bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg ${animate ? 'animate-fadeIn' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">{title}</div>
        <div className="opacity-80 text-xs">{issues?.length || 0} item(s)</div>
      </div>

      {issues && issues.length > 0 ? (
        <ul className="space-y-2">
          {issues.map((it) => (
            <li key={it.key} className="bg-secondary-800 border border-secondary-700 rounded-md p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-white font-medium truncate">
                    {it.key}
                    {it.summary ? <span className="opacity-80 font-normal"> — {it.summary}</span> : null}
                  </div>
                  <div className="text-xs text-gray-300 mt-1 flex gap-2 flex-wrap">
                    {it.status ? <span className="px-1.5 py-0.5 rounded bg-secondary-700 border border-secondary-600">{it.status}</span> : null}
                    {it.priority ? <span className="px-1.5 py-0.5 rounded bg-secondary-700 border border-secondary-600">{it.priority}</span> : null}
                  </div>
                </div>
                {it.url ? (
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 text-xs text-primary-300 hover:text-primary-200 underline"
                    title="Open in Jira"
                  >
                    Open
                  </a>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="opacity-80 italic">No issues found.</div>
      )}
    </div>
  )
}
