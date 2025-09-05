import { useEffect, useState } from 'react'
import { motion, type Variants } from 'framer-motion'

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

const listVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12,
    },
  },
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
}


export default function IssueList({ data }: { data: IssueListData }) {
  const { title = 'Issues', issues } = data
  const [animate, setAnimate] = useState(false) //type:ignore
  const jiraBase = (typeof window !== 'undefined' && localStorage.getItem('jira_base')) || ''
  const normalizedBase = jiraBase && jiraBase.endsWith('/') ? jiraBase.slice(0, -1) : jiraBase

  useEffect(() => {
    setAnimate(false)
    void document.getElementById('issue-list-card')?.offsetWidth
    setAnimate(true)
  }, [JSON.stringify(issues), title])

  return (
    <motion.div
      id="issue-list-card"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-lg text-primary-400">{title}</div>
        <div className="opacity-80 text-xs">{issues?.length || 0} item(s)</div>
      </div>

      {issues && issues.length > 0 ? (
        <motion.ul
          variants={listVariants}
          initial="hidden"
          animate="show"
          className="space-y-2"
        >
          {issues.map((it) => (
            <motion.li
              key={it.key}
              variants={itemVariants}
              className="bg-secondary-800 border border-secondary-700 rounded-md p-0 shadow hover:shadow-[0_0_12px_rgba(0,255,255,0.4)] transition overflow-hidden"
            >
              {(() => {
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
                return href ? (
                  <a href={href} target="_blank" rel="noreferrer" className="block hover:bg-secondary-750/40">
                    {inner}
                  </a>
                ) : inner
              })()}
            </motion.li>
          ))}
        </motion.ul>
      ) : (
        <div className="opacity-80 italic">No issues found.</div>
      )}
    </motion.div>
  )
}
