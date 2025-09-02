import React from 'react'

export type JiraStatusData = {
  key: string
  name: string | null
  expectedFinishDate: string | null
  comments: string[]
}

export default function JiraStatus({ data }: { data: JiraStatusData }) {
  const { key, name, expectedFinishDate, comments } = data

  return (
    <div className="bg-secondary-900 border border-secondary-700 rounded-lg p-3 text-gray-200 text-sm max-w-full">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-base">Jira Issue: {key}</div>
        <div className="opacity-90">
          {expectedFinishDate ? `Due: ${expectedFinishDate}` : 'No due date'}
        </div>
      </div>
      <div className="mb-2">
        <span className="opacity-85">Name: </span>
        <span>{name || '(no summary)'}</span>
      </div>
      <div>
        <div className="mb-1">Comments:</div>
        {comments && comments.length > 0 ? (
          <ul className="list-disc pl-4">
            {comments.slice(0, 5).map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : (
          <div className="opacity-80">(no comments)</div>
        )}
      </div>
    </div>
  )
}
