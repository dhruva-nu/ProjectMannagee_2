import React from 'react'

export type JiraStatusData = {
  key: string
  name: string | null
  expectedFinishDate: string | null
  comments: string[]
}

export default function JiraStatus({ data }: { data: JiraStatusData }) {
  const { key, name, expectedFinishDate, comments } = data

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

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.title}>Jira Issue: {key}</div>
        <div style={styles.meta}>{expectedFinishDate ? `Due: ${expectedFinishDate}` : 'No due date'}</div>
      </div>
      <div style={{ marginBottom: 8 }}>
        <span style={styles.label}>Name: </span>
        <span>{name || '(no summary)'}</span>
      </div>
      <div>
        <div style={{ marginBottom: 4 }}>Comments:</div>
        {comments && comments.length > 0 ? (
          <ul style={styles.list}>
            {comments.slice(0, 5).map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : (
          <div style={{ opacity: 0.8 }}>(no comments)</div>
        )}
      </div>
    </div>
  )
}
