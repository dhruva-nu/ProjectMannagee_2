export type SprintStatusData = {
  name: string | null
  startDate: string | null
  endDate: string | null
  notes?: string[]
}

export default function SprintStatus({ data }: { data: SprintStatusData }) {
  const { name, startDate, endDate, notes } = data

  const dateRange = startDate || endDate ? `${startDate || 'Unknown'} → ${endDate || 'Unknown'}` : 'No dates'

  return (
    <div className="bg-secondary-900 border border-secondary-700 rounded-lg p-3 text-gray-200 text-sm max-w-full">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-base">Sprint</div>
        <div className="opacity-90">{dateRange}</div>
      </div>
      <div className="mb-2">
        <span className="opacity-85">Name: </span>
        <span>{name || '(no sprint name)'}</span>
      </div>
      <div>
        <div className="mb-1">Notes:</div>
        {notes && notes.length > 0 ? (
          <ul className="list-disc pl-4">
            {notes.slice(0, 5).map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        ) : (
          <div className="opacity-80">(no notes)</div>
        )}
      </div>
    </div>
  )
}
