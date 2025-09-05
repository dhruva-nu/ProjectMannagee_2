// React import not required with modern JSX runtime

export type WorkdayIssue = {
  key: string
  summary?: string
  status?: string
  due?: string
  url?: string
}

export type WorkdaySummaryData = {
  mode: 'start' | 'end'
  // Common
  title?: string

  // Start mode
  startedAt?: string
  trackingRepo?: string
  trackingBranch?: string
  dueToday?: WorkdayIssue[]
  nextUp?: WorkdayIssue[]

  // End mode
  since?: string
  jira?: {
    completed?: number | string
    raised?: number | string
    working?: number | string
  }
  github?: {
    repo?: string
    summaryText?: string
  }
}

export default function WorkdaySummary({ data }: { data: WorkdaySummaryData }) {
  const { mode } = data

  return (
    <div className="bg-secondary-900 border border-secondary-700 rounded-xl p-4 text-gray-200 text-sm w-full">
      <div className="text-base font-semibold text-white mb-2">
        {data.title || (mode === 'start' ? 'Workday started' : 'Workday summary')}
      </div>

      {mode === 'start' ? (
        <div className="space-y-3">
          {data.startedAt && (
            <div className="text-gray-300">Started at: <span className="text-gray-100">{data.startedAt}</span></div>
          )}
          {(data.trackingRepo || data.trackingBranch) && (
            <div className="text-gray-300">
              Tracking: <span className="text-gray-100">{data.trackingRepo}{data.trackingBranch ? `@${data.trackingBranch}` : ''}</span>
            </div>
          )}

          <div>
            <div className="text-white font-medium">Due today</div>
            <ul className="mt-1 list-disc list-inside space-y-1">
              {(data.dueToday && data.dueToday.length > 0) ? (
                data.dueToday.map((it, idx) => (
                  <li key={`${it.key}-${idx}`} className="text-gray-200">
                    <span className="font-mono text-cyan-300">{it.key}</span>
                    {it.summary ? `: ${it.summary}` : ''}
                    {it.due ? ` (${it.due})` : ''}
                  </li>
                ))
              ) : (
                <li className="text-gray-400">None</li>
              )}
            </ul>
          </div>

          <div>
            <div className="text-white font-medium">In progress / next up</div>
            <ul className="mt-1 list-disc list-inside space-y-1">
              {(data.nextUp && data.nextUp.length > 0) ? (
                data.nextUp.map((it, idx) => (
                  <li key={`${it.key}-${idx}`} className="text-gray-200">
                    <span className="font-mono text-cyan-300">{it.key}</span>
                    {it.summary ? `: ${it.summary}` : ''}
                    {it.status ? ` [${it.status}]` : ''}
                  </li>
                ))
              ) : (
                <li className="text-gray-400">None</li>
              )}
            </ul>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {data.since && (
            <div className="text-gray-300">Since: <span className="text-gray-100">{data.since}</span></div>
          )}
          {data.jira && (
            <div>
              <div className="text-white font-medium">Jira</div>
              <ul className="mt-1 list-disc list-inside space-y-1">
                <li className="text-gray-200">Completed issues: {String(data.jira.completed ?? 'n/a')}</li>
                <li className="text-gray-200">Raised issues: {String(data.jira.raised ?? 'n/a')}</li>
                <li className="text-gray-200">Working on: {String(data.jira.working ?? 'n/a')}</li>
              </ul>
            </div>
          )}
          {data.github && (
            <div>
              <div className="text-white font-medium">GitHub commits</div>
              {data.github.repo && (
                <div className="text-gray-300">Repository: <span className="text-gray-100">{data.github.repo}</span></div>
              )}
              {data.github.summaryText && (
                <pre className="mt-1 whitespace-pre-wrap break-words text-gray-200 bg-secondary-800 p-2 rounded-md border border-secondary-700 text-xs">
                  {data.github.summaryText}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
