import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'

export type EtaEstimateData = {
  issue: string
  project_key: string
  optimistic_days: number
  pessimistic_days: number
  optimistic_critical_path?: string[]
  pessimistic_blockers?: string[]
  nodes: Record<
    string,
    {
      assignee?: string
      duration_days: number
      dependencies: string[]
    }
  >
  summary?: string
}

function Tree({
  root,
  nodes,
  visited = new Set<string>(),
  depth = 0,
}: {
  root: string
  nodes: EtaEstimateData['nodes']
  visited?: Set<string>
  depth?: number
}) {
  const nd = nodes[root]
  const isCycle = visited.has(root)
  const deps = nd?.dependencies || []
  const nextVisited = new Set(visited)
  nextVisited.add(root)
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
      className="ml-3"
    >
      <div className="flex items-center gap-2">
        <div
          className={`text-xs px-2 py-1 rounded shadow-md ${depth === 0
              ? 'bg-primary-700 text-white'
              : 'bg-secondary-700 text-gray-100'
            }`}
        >
          {root}
        </div>
        {nd && (
          <div className="text-xs opacity-80">
            {nd.duration_days}d{nd.assignee ? ` • ${nd.assignee}` : ''}
          </div>
        )}
        {isCycle && <div className="text-[10px] text-red-400">cycle</div>}
      </div>
      {!isCycle && deps.length > 0 && (
        <div className="mt-1 border-l border-secondary-600 pl-3">
          {deps.map((d) => (
            <Tree
              key={d}
              root={d}
              nodes={nodes}
              visited={nextVisited}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </motion.div>
  )
}

export default function EtaEstimate({ data }: { data: EtaEstimateData }) {
  const {
    issue,
    optimistic_days,
    pessimistic_days,
    nodes,
    summary,
    optimistic_critical_path = [],
    pessimistic_blockers = [],
  } = data
  const [, setAnimate] = useState(false)

  useEffect(() => {
    setAnimate(false)
    void document.getElementById('eta-estimate-card')?.offsetWidth
    setAnimate(true)
  }, [data])

  const total = Math.max(optimistic_days || 0, pessimistic_days || 0, 1)
  const widths = useMemo(() => {
    const maxWidth = 260
    const optW = Math.max(
      6,
      Math.round((Math.min(optimistic_days, total) / total) * maxWidth)
    )
    const pesW = Math.max(
      6,
      Math.round((Math.min(pessimistic_days, total) / total) * maxWidth)
    )
    return { optW, pesW }
  }, [optimistic_days, pessimistic_days, total])

  return (
    <motion.div
      id="eta-estimate-card"
      initial={{ opacity: 0, scale: 0.9, rotateY: 45 }}
      animate={{ opacity: 1, scale: 1, rotateY: 0 }}
      whileHover={{
        scale: 1.02,
        boxShadow: '0 0 30px rgba(0, 255, 255, 0.6)',
        rotateX: 3,
        rotateY: -3,
      }}
      transition={{ duration: 0.6, ease: 'easeInOut' }}
      className="bg-secondary-900 border border-secondary-700 rounded-2xl p-4 text-gray-200 text-sm w-full max-w-full shadow-lg relative overflow-hidden"
    >
      {/* neon background glow */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 via-purple-500/20 to-pink-500/20 blur-2xl"
        animate={{ opacity: [0.3, 0.6, 0.3], scale: [1, 1.2, 1] }}
        transition={{ duration: 6, repeat: Infinity, repeatType: 'mirror' }}
      />

      <div className="flex items-center justify-between mb-3 relative z-10">
        <div className="font-bold text-lg text-primary-400 tracking-wide">
          ETA Estimate: {issue}
        </div>
        <div className="text-xs opacity-80">Optimistic–Pessimistic</div>
      </div>

      {/* bars */}
      <div className="mb-3 relative z-10">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-24 text-xs opacity-70">Optimistic</div>
          <motion.div
            className="h-3 bg-primary-700 rounded shadow-[0_0_12px_rgba(0,255,255,0.7)]"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: widths.optW, opacity: 1 }}
            transition={{ duration: 1.2, ease: 'easeOut' }}
          />
          <div className="text-xs">{optimistic_days}d</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-24 text-xs opacity-70">Pessimistic</div>
          <motion.div
            className="h-3 bg-accent-cyan rounded shadow-[0_0_12px_rgba(0,255,255,0.7)]"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: widths.pesW, opacity: 1 }}
            transition={{ duration: 1.5, ease: 'easeOut', delay: 0.2 }}
          />
          <div className="text-xs">
            {Math.max(pessimistic_days, optimistic_days)}d
          </div>
        </div>
      </div>


      {/* summary */}
      {summary && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mb-3 text-xs opacity-85 relative z-10"
        >
          {summary}
        </motion.div>
      )}

      {/* dependency graph & blockers */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 relative z-10">
        <div>
          <div className="font-semibold text-primary-300 mb-2">
            Dependency Graph
          </div>
          <Tree root={issue} nodes={nodes} />
        </div>
        <div>
          {optimistic_critical_path.length > 0 && (
            <div className="mb-3">
              <div className="font-semibold text-primary-300 mb-1">
                Optimistic Critical Path
              </div>
              <div className="flex flex-wrap gap-1">
                {optimistic_critical_path.map((k, i) => (
                  <motion.span
                    key={k + String(i)}
                    className="text-[11px] px-2 py-1 bg-secondary-700 rounded shadow-sm"
                    whileHover={{ scale: 1.1, backgroundColor: '#0ea5e9' }}
                  >
                    {k}
                  </motion.span>
                ))}
              </div>
            </div>
          )}
          {pessimistic_blockers.length > 0 && (
            <div>
              <div className="font-semibold text-primary-300 mb-1">
                Pessimistic Blockers
              </div>
              <div className="flex flex-wrap gap-1">
                {pessimistic_blockers.map((k, i) => (
                  <motion.span
                    key={k + String(i)}
                    className="text-[11px] px-2 py-1 bg-secondary-700 rounded shadow-sm"
                    whileHover={{ scale: 1.1, backgroundColor: '#ef4444' }}
                  >
                    {k}
                  </motion.span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
