import { useEffect, useMemo, useState } from 'react'

export type UserCardData = {
  name: string
  designation?: string
  email?: string
  avatarUrl?: string
  online?: boolean
}

export default function UserCard({ data }: { data: UserCardData }) {
  const { name } = data
  const [animate, setAnimate] = useState(false)

  const computed = useMemo(() => {
    const trimmed = (name || '').trim()
    const parts = trimmed.split(/\s+/)
    const first = parts[0] || 'user'
    const last = parts.slice(1).join(' ')

    const slug = trimmed.toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/^\.|\.$/g, '') || 'user'
    const email = data.email || (last ? `${first.toLowerCase()}.${last.toLowerCase().replace(/\s+/g,'.')}@example.com` : `${slug}@example.com`)

    const designation = data.designation || 'Software Engineer'

    const avatarUrl = data.avatarUrl || `https://ui-avatars.com/api/?name=${encodeURIComponent(trimmed)}&background=0D8ABC&color=fff&size=128`

    const online = typeof data.online === 'boolean' ? data.online : Math.random() > 0.5

    return { email, designation, avatarUrl, online }
  }, [name, data.email, data.designation, data.avatarUrl, data.online])

  useEffect(() => {
    setAnimate(false)
    void document.getElementById('user-card')?.offsetWidth
    setAnimate(true)
  }, [data])

  return (
    <div id="user-card" className={`bg-secondary-900 border border-secondary-700 rounded-lg p-4 text-gray-200 text-sm max-w-full shadow-lg ${animate ? 'animate-fadeIn' : ''}`}>
      <div className="flex items-center gap-4">
        <div className="relative">
          <img
            src={computed.avatarUrl}
            alt={name}
            className="w-14 h-14 rounded-full border border-secondary-700 object-cover"
          />
          <span
            title={computed.online ? 'Online' : 'Offline'}
            className={`absolute bottom-0 right-0 block w-3.5 h-3.5 rounded-full ring-2 ring-secondary-900 ${computed.online ? 'bg-green-500' : 'bg-red-500'}`}
          />
        </div>
        <div>
          <div className="text-lg font-semibold text-white">{name}</div>
          <div className="text-xs text-primary-300">{computed.designation}</div>
          <div className="text-xs text-gray-300 mt-1">{computed.email}</div>
        </div>
      </div>
    </div>
  )
}
