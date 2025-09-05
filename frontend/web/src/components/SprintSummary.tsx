import { motion } from 'framer-motion'
import type { IssueListItem } from './IssueList'

export type SprintSummaryData = {
  // Existing fields (optional)
  project?: string
  total_issues?: number
  status_categories?: Record<string, number> // Changed from status_counts
  sample_issues?: IssueListItem[]
  // New minimal summary fields
  sprintName?: string
  startDate?: string
  endDate?: string
}

function formatRange(start?: string, end?: string) {
  if (!start && !end) return undefined
  const s = start ? new Date(start).toLocaleString() : 'Unknown'
  const e = end ? new Date(end).toLocaleString() : 'Unknown'
  return `${s} → ${e}`
}

export default function SprintSummary({ data }: { data: SprintSummaryData }) {
  const {
    project,
    total_issues = 0,
    status_categories = {}, // Changed from status_counts
    sample_issues = [],
    sprintName,
    startDate,
    endDate,
  } = data || ({} as SprintSummaryData)
  const jiraBase = (typeof window !== 'undefined' && localStorage.getItem('jira_base')) || ''
  const normalizedBase = jiraBase && jiraBase.endsWith('/') ? jiraBase.slice(0, -1) : jiraBase
  const statuses = Object.entries(status_categories || {})
  const dateRange = formatRange(startDate, endDate)

  return (
    <motion.div
      id="sprint-summary-card"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">Sprint Summary{sprintName ? `: ${sprintName}` : ''}</div>
        {(project || dateRange) && (
          <div className="opacity-80 text-xs flex gap-3">
            {project ? (
              <div>
                Project: <span className="text-white font-medium">{project}</span>
              </div>
            ) : null}
            {dateRange ? (
              <div className="opacity-90">{dateRange}</div>
            ) : null}
          </div>
        )}
      </div>

      {(typeof total_issues === 'number' || statuses.length > 0) && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-secondary-800 rounded-md p-3 border border-secondary-700">
            <div className="text-xs opacity-75">Total Issues</div>
            <div className="text-white text-base font-semibold">{typeof total_issues === 'number' ? total_issues : 0}</div>
          </div>
          <div className="col-span-2 bg-secondary-800 rounded-md p-3 border border-secondary-700">
            <div className="text-xs opacity-75 mb-2">Status Counts</div>
            {statuses.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {statuses.map(([name, cnt]) => (
                  <span key={name} className="text-xs px-2 py-1 rounded bg-secondary-700 border border-secondary-600">
                    {name}: <span className="text-white font-medium">{cnt}</span>
                  </span>
                ))}
              </div>
            ) : (
              <div className="opacity-75 text-xs">No status data</div>
            )}
          </div>
        </div>
      )}

      {Array.isArray(sample_issues) && sample_issues.length > 0 && (
        <div>
          <div className="font-semibold mb-2 text-primary-300">Sample Issues</div>
          <ul className="space-y-2">
            {sample_issues.slice(0, 5).map((it) => {
              const href = it.url || (normalizedBase ? `${normalizedBase}/browse/${it.key}` : undefined)
              const inner = (
                <div className="flex items-start justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <div className="text-white font-medium truncate">
                      {it.key}
                      {it.summary ? (
                        <span className="opacity-80 font-normal"> — {it.summary}</span>
                      ) : null}
                    </div>
                    <div className="text-xs text-gray-300 mt-1 flex gap-2 flex-wrap">
                      {it.status ? (
                        <span className="px-1.5 py-0.5 rounded bg-secondary-700 border border-secondary-600">
                          {it.status}
                        </span>
                      ) : null}
                      {it.priority ? (
                        <span className="px-1.5 py-0.5 rounded bg-secondary-700 border border-secondary-600">
                          {it.priority}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {href ? (
                    <span className="shrink-0 text-xs text-primary-300 hover:text-primary-200 underline" title="Open in Jira">
                      Open
                    </span>
                  ) : null}
                </div>
              )
              return (
                <li key={it.key} className="bg-secondary-800 border border-secondary-700 rounded-md p-0 overflow-hidden">
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer" className="block hover:bg-secondary-750/40">
                      {inner}
                    </a>
                  ) : inner}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </motion.div>
  )
}
