import { useEffect, useState } from 'react'

export type SprintStatusData = {
  name: string | null
  startDate: string | null
  endDate: string | null
  notes?: string[]
  totalIssues?: number
  completedIssues?: number
}

export default function SprintStatus({ data }: { data: SprintStatusData }) {
  const { name, startDate, endDate, notes, totalIssues = 0, completedIssues = 0 } = data

  const [animate, setAnimate] = useState(false)

  useEffect(() => {
    setAnimate(false)
    // Force reflow to restart animation
    void document.getElementById('sprint-status-card')?.offsetWidth
    setAnimate(true)
  }, [data])

  const dateRange = startDate || endDate ? `${startDate || 'Unknown'} → ${endDate || 'Unknown'}` : 'No dates'
  const safeTotal = Math.max(0, totalIssues)
  const safeDone = Math.min(Math.max(0, completedIssues), safeTotal)
  const pct = safeTotal === 0 ? 0 : Math.round((safeDone / safeTotal) * 100)

  return (
    <div id="sprint-status-card" className={`bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg ${animate ? 'animate-fadeIn' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">Sprint</div>
        <div className="opacity-90 text-xs sm:text-sm">{dateRange}</div>
      </div>
      <div className="mb-3">
        <span className="opacity-85">Name: </span>
        <span className="text-white">{name || '(no sprint name)'}</span>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-3">
        <div className="bg-secondary-800 rounded-md p-2 border border-secondary-700">
          <div className="text-xs opacity-75">Total Issues</div>
          <div className="text-white text-base font-semibold">{safeTotal}</div>
        </div>
        <div className="bg-secondary-800 rounded-md p-2 border border-secondary-700">
          <div className="text-xs opacity-75">Completed</div>
          <div className="text-white text-base font-semibold">{safeDone}</div>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <div className="font-semibold text-primary-300">Progress</div>
          <div className="text-xs opacity-80">{pct}%</div>
        </div>
        <div className="h-2 w-full bg-secondary-800 rounded-full overflow-hidden border border-secondary-700">
          <div
            className="h-full bg-primary-600"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div>
        <div className="font-semibold mb-2 text-primary-300">Notes:</div>
        {notes && notes.length > 0 ? (
          <ul className="list-disc list-inside pl-2 space-y-1">
            {notes.slice(0, 5).map((n, i) => (
              <li key={i} className="text-gray-300">{n}</li>
            ))}
          </ul>
        ) : (
          <div className="opacity-80 italic">(no notes)</div>
        )}
      </div>
    </div>
  )
}
