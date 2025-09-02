import { useState } from 'react'

type Props = {
  onInsertProject: (projectKey: string) => void
  onInsertIssue: (issueKey: string) => void
}

export default function IssueQuickAdd({ onInsertProject, onInsertIssue }: Props) {
  const [projectKey, setProjectKey] = useState('')
  const [issueKey, setIssueKey] = useState('')

  const insertProject = () => {
    const pk = projectKey.trim()
    if (!pk) return
    onInsertProject(pk)
  }

  const insertIssue = () => {
    const pk = projectKey.trim()
    const ik = issueKey.trim()
    if (!pk && !ik) return
    // If user typed full key in issue input (like PROJ-123), use it directly; else compose from pk+ik
    const text = pk && ik ? `${pk}-${ik}` : ik
    if (!text) return
    onInsertIssue(text)
    setIssueKey('')
  }

  return (
    <div className="w-full max-w-[500px] flex items-end gap-2 mb-6">
      <div className="flex-1">
        <label className="block text-sm mb-1 text-gray-300">Project Key</label>
        <input
          className="w-full px-3 py-2 rounded-lg border border-secondary-600 bg-secondary-900 text-white"
          placeholder="e.g. PROJ"
          value={projectKey}
          onChange={(e) => setProjectKey(e.target.value.toUpperCase())}
        />
      </div>
      <div className="flex-1">
        <label className="block text-sm mb-1 text-gray-300">Issue Key</label>
        <input
          className="w-full px-3 py-2 rounded-lg border border-secondary-600 bg-secondary-900 text-white"
          placeholder="e.g. 123 or PROJ-123"
          value={issueKey}
          onChange={(e) => setIssueKey(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === 'Enter') insertIssue()
          }}
        />
      </div>
      <div className="flex gap-2">
        <button
          className="px-3 py-2 h-[42px] rounded-lg border border-secondary-600 bg-secondary-700 hover:bg-secondary-600 text-white"
          onClick={insertProject}
        >
          Insert Project
        </button>
        <button
          className="px-3 py-2 h-[42px] rounded-lg border border-secondary-600 bg-primary-600 hover:bg-primary-500 text-white"
          onClick={insertIssue}
        >
          Insert Issue
        </button>
      </div>
    </div>
  )
}
