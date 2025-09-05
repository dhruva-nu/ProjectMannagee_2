import { useEffect, useState } from 'react'
import { motion, type Variants } from 'framer-motion'

export type JiraStatusData = {
  key: string
  name: string | null
  expectedFinishDate: string | null
  status: string
  comments: string[]
  url?: string
}

const commentsVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12,
    },
  },
}

const commentItem: Variants = {
  hidden: { opacity: 0, x: -10 },
  show: { opacity: 1, x: 0, transition: { duration: 0.4, ease: 'easeOut' } },
}

export default function JiraStatus({ data }: { data: JiraStatusData }) {
  const { key, name, expectedFinishDate, status, comments } = data
  const jiraBase = (typeof window !== 'undefined' && localStorage.getItem('jira_base')) || ''
  const issueUrl = data.url || (jiraBase ? `${jiraBase.replace(/\/$/, '')}/browse/${key}` : undefined)
  const [animate, setAnimate] = useState(false)

  useEffect(() => {
    setAnimate(false)
    // Force reflow to restart animation
    void document.getElementById('jira-status-card')?.offsetWidth
    setAnimate(true)
  }, [data])

  return (
    <motion.div
      id="jira-status-card"
      initial={{ opacity: 0, scale: 0.95, rotateY: 20 }}
      animate={{ opacity: 1, scale: 1, rotateY: 0 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      whileHover={{
        scale: 1.02,
        boxShadow: '0 0 30px rgba(0, 255, 255, 0.6)',
      }}
      className="relative bg-secondary-900 border border-secondary-700 rounded-2xl p-4 text-gray-200 text-sm max-w-full shadow-lg overflow-hidden"
    >
      {/* glowing animated background */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 via-purple-500/20 to-pink-500/20 blur-2xl"
        animate={{ opacity: [0.3, 0.6, 0.3], scale: [1, 1.2, 1] }}
        transition={{ duration: 6, repeat: Infinity, repeatType: 'mirror' }}
      />

      <div className="flex items-center justify-between mb-3 relative z-10">
        <div className="font-bold text-lg text-primary-400">
          {issueUrl ? (
            <a
              href={issueUrl}
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
              title="Open in Jira"
            >
              Jira Issue: {key}
            </a>
          ) : (
            <>Jira Issue: {key}</>
          )}
        </div>
        <motion.div
          className="text-accent-cyan font-semibold text-base"
          animate={{ opacity: [1, 0.7, 1] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          Status: {status}
        </motion.div>
      </div>

      <div className="mb-2 relative z-10">
        <span className="opacity-85">Summary: </span>
        <span className="text-white">{name || '(no summary)'}</span>
      </div>
      <div className="mb-3 text-xs opacity-75 relative z-10">
        {expectedFinishDate ? `Due: ${expectedFinishDate}` : 'No due date'}
      </div>

      <div className="relative z-10">
        <div className="font-semibold mb-2 text-primary-300">Comments:</div>
        {comments && comments.length > 0 ? (
          <motion.ul
            variants={commentsVariants}
            initial="hidden"
            animate="show"
            className="list-disc list-inside pl-2 space-y-1"
          >
            {comments.slice(0, 5).map((c, i) => (
              <motion.li
                key={i}
                variants={commentItem}
                className="text-gray-300"
              >
                {c}
              </motion.li>
            ))}
          </motion.ul>
        ) : (
          <div className="opacity-80 italic">(no comments)</div>
        )}
      </div>
    </motion.div>
  )
}
