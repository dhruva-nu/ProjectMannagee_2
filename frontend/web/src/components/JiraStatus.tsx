import { useEffect, useState } from 'react'

export type JiraStatusData = {
  key: string
  name: string | null
  expectedFinishDate: string | null
  status: string
  comments: string[]
}

export default function JiraStatus({ data }: { data: JiraStatusData }) {
  const { key, name, expectedFinishDate, status, comments } = data
  const [animate, setAnimate] = useState(false)

  useEffect(() => {
    setAnimate(false)
    // Force reflow to restart animation
    void document.getElementById('jira-status-card')?.offsetWidth
    setAnimate(true)
  }, [data]) // Re-run effect when data changes

  return (
    <div id="jira-status-card" className={`bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg ${animate ? 'animate-fadeIn' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">Jira Issue: {key}</div>
        <div className="text-accent-cyan font-semibold text-base">Status: {status}</div>
      </div>
      <div className="mb-2">
        <span className="opacity-85">Summary: </span>
        <span className="text-white">{name || '(no summary)'}</span>
      </div>
      <div className="mb-3 text-xs opacity-75">
        {expectedFinishDate ? `Due: ${expectedFinishDate}` : 'No due date'}
      </div>
      <div>
        <div className="font-semibold mb-2 text-primary-300">Comments:</div>
        {comments && comments.length > 0 ? (
          <ul className="list-disc list-inside pl-2 space-y-1">
            {comments.slice(0, 5).map((c, i) => (
              <li key={i} className="text-gray-300">{c}</li>
            ))}
          </ul>
        ) : (
          <div className="opacity-80 italic">(no comments)</div>
        )}
      </div>
    </div>
  )
}
