import React from 'react'

export type SprintStatusData = {
  name: string | null
  startDate: string | null
  endDate: string | null
  notes?: string[]
}

export default function SprintStatus({ data }: { data: SprintStatusData }) {
  const { name, startDate, endDate, notes } = data

  const styles: Record<string, React.CSSProperties> = {
    card: {
      background: '#0f1115',
      border: '1px solid #272a31',
      borderRadius: 10,
      padding: 12,
      color: '#e5e7eb',
      fontSize: 13,
      maxWidth: '100%',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 8,
    },
    title: { fontWeight: 600, fontSize: 14 },
    meta: { opacity: 0.9 },
    list: { margin: 0, paddingLeft: 16 },
    label: { opacity: 0.85 },
  }

  const dateRange = startDate || endDate ? `${startDate || 'Unknown'} → ${endDate || 'Unknown'}` : 'No dates'

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.title}>Sprint</div>
        <div style={styles.meta}>{dateRange}</div>
      </div>
      <div style={{ marginBottom: 8 }}>
        <span style={styles.label}>Name: </span>
        <span>{name || '(no sprint name)'}</span>
      </div>
      <div>
        <div style={{ marginBottom: 4 }}>Notes:</div>
        {notes && notes.length > 0 ? (
          <ul style={styles.list}>
            {notes.slice(0, 5).map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        ) : (
          <div style={{ opacity: 0.8 }}>(no notes)</div>
        )}
      </div>
    </div>
  )
}
