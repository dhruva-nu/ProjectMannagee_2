import { useMemo } from 'react'

export type EtaEstimateData = {
  issue: string
  project_key: string
  optimistic_days: number
  pessimistic_days: number
  optimistic_critical_path?: string[]
  pessimistic_blockers?: string[]
  nodes: Record<string, {
    assignee?: string
    duration_days: number
    dependencies: string[]
  }>
  summary?: string
}

function Tree({ root, nodes, visited = new Set<string>(), depth = 0 }: { root: string; nodes: EtaEstimateData['nodes']; visited?: Set<string>; depth?: number }) {
  const nd = nodes[root]
  const isCycle = visited.has(root)
  const deps = nd?.dependencies || []
  const nextVisited = new Set(visited)
  nextVisited.add(root)
  return (
    <div className="ml-3">
      <div className="flex items-center gap-2">
        <div className={`text-xs px-2 py-1 rounded ${depth === 0 ? 'bg-primary-700 text-white' : 'bg-secondary-700 text-gray-100'}`}>{root}</div>
        {nd && (
          <div className="text-xs opacity-80">{nd.duration_days}d{nd.assignee ? ` • ${nd.assignee}` : ''}</div>
        )}
        {isCycle && <div className="text-[10px] text-red-400">cycle</div>}
      </div>
      {!isCycle && deps.length > 0 && (
        <div className="mt-1 border-l border-secondary-600 pl-3">
          {deps.map((d) => (
            <Tree key={d} root={d} nodes={nodes} visited={nextVisited} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function EtaEstimate({ data }: { data: EtaEstimateData }) {
  const { issue, optimistic_days, pessimistic_days, nodes, summary, optimistic_critical_path = [], pessimistic_blockers = [] } = data

  const total = Math.max(optimistic_days || 0, pessimistic_days || 0, 1)
  const widths = useMemo(() => {
    const maxWidth = 260
    const optW = Math.max(6, Math.round((Math.min(optimistic_days, total) / total) * maxWidth))
    const pesW = Math.max(6, Math.round((Math.min(pessimistic_days, total) / total) * maxWidth))
    return { optW, pesW }
  }, [optimistic_days, pessimistic_days, total])

  return (
    <div className="bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm w-full max-w-full">
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">ETA Estimate: {issue}</div>
        <div className="text-xs opacity-80">Optimistic–Pessimistic</div>
      </div>

      <div className="mb-3">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-24 text-xs opacity-70">Optimistic</div>
          <div className="h-3 bg-primary-700 rounded" style={{ width: widths.optW }} />
          <div className="text-xs">{optimistic_days}d</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-24 text-xs opacity-70">Pessimistic</div>
          <div className="h-3 bg-accent-cyan rounded" style={{ width: widths.pesW }} />
          <div className="text-xs">{Math.max(pessimistic_days, optimistic_days)}d</div>
        </div>
      </div>

      {summary && (
        <div className="mb-3 text-xs opacity-85">{summary}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="font-semibold text-primary-300 mb-2">Dependency Graph</div>
          <Tree root={issue} nodes={nodes} />
        </div>
        <div>
          {optimistic_critical_path.length > 0 && (
            <div className="mb-3">
              <div className="font-semibold text-primary-300 mb-1">Optimistic Critical Path</div>
              <div className="flex flex-wrap gap-1">
                {optimistic_critical_path.map((k, i) => (
                  <span key={k+String(i)} className="text-[11px] px-2 py-1 bg-secondary-700 rounded">
                    {k}
                  </span>
                ))}
              </div>
            </div>
          )}
          {pessimistic_blockers.length > 0 && (
            <div>
              <div className="font-semibold text-primary-300 mb-1">Pessimistic Blockers</div>
              <div className="flex flex-wrap gap-1">
                {pessimistic_blockers.map((k, i) => (
                  <span key={k+String(i)} className="text-[11px] px-2 py-1 bg-secondary-700 rounded">
                    {k}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
