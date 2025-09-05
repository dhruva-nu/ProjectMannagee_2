import { useMemo } from 'react'
import { motion } from 'framer-motion'

export type UserCardData = {
  name: string
  designation?: string
  email?: string
  avatarUrl?: string
  online?: boolean
}

export default function UserCard({ data }: { data: UserCardData }) {
  const { name } = data

  const computed = useMemo(() => {
    const trimmed = (name || '').trim()
    const parts = trimmed.split(/\s+/)
    const first = parts[0] || 'user'
    const last = parts.slice(1).join(' ')

    const slug =
      trimmed.toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/^\.|\.$/g, '') ||
      'user'

    const email =
      data.email ||
      (last
        ? `${first.toLowerCase()}.${last
            .toLowerCase()
            .replace(/\s+/g, '.') }@example.com`
        : `${slug}@example.com`)

    const designation = data.designation || 'Software Engineer'

    const avatarUrl =
      data.avatarUrl ||
      `https://ui-avatars.com/api/?name=${encodeURIComponent(
        trimmed
      )}&background=0D8ABC&color=fff&size=128`

    const online =
      typeof data.online === 'boolean' ? data.online : Math.random() > 0.5

    return { email, designation, avatarUrl, online }
  }, [name, data.email, data.designation, data.avatarUrl, data.online])

  return (
    <motion.div
      id="user-card"
      initial={{ opacity: 0, scale: 0.9, rotateY: 45 }}
      animate={{ opacity: 1, scale: 1, rotateY: 0 }}
      whileHover={{
        scale: 1.05,
        boxShadow: '0 0 30px rgba(0, 255, 255, 0.6)',
        rotateX: 5,
        rotateY: -5,
      }}
      transition={{
        duration: 0.6,
        ease: 'easeInOut',
      }}
      className="bg-secondary-900 border border-secondary-700 rounded-2xl p-4 text-gray-200 text-sm max-w-full shadow-lg relative overflow-hidden"
    >
      {/* glowing background animation */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 via-purple-500/20 to-pink-500/20 blur-2xl"
        animate={{ opacity: [0.3, 0.6, 0.3], scale: [1, 1.2, 1] }}
        transition={{ duration: 6, repeat: Infinity, repeatType: 'mirror' }}
      />

      <div className="flex items-center gap-4 relative z-10">
        <div className="relative">
          <motion.img
            src={computed.avatarUrl}
            alt={name}
            className="w-16 h-16 rounded-full border border-cyan-400 object-cover shadow-[0_0_20px_rgba(0,255,255,0.5)]"
            animate={{ rotate: [0, 5, -5, 0] }}
            transition={{ duration: 6, repeat: Infinity }}
          />
          <motion.span
            title={computed.online ? 'Online' : 'Offline'}
            className={`absolute bottom-0 right-0 block w-3.5 h-3.5 rounded-full ring-2 ring-secondary-900 ${
              computed.online ? 'bg-green-500' : 'bg-red-500'
            }`}
            animate={{
              scale: computed.online ? [1, 1.3, 1] : [1],
              opacity: computed.online ? [1, 0.6, 1] : [1],
            }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              repeatType: 'mirror',
            }}
          />
        </div>
        <div>
          <div className="text-lg font-semibold text-white tracking-wide">
            {name}
          </div>
          <div className="text-xs text-cyan-300">{computed.designation}</div>
          <div className="text-xs text-gray-300 mt-1">{computed.email}</div>
        </div>
      </div>
    </motion.div>
  )
}
