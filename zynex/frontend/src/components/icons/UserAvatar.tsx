import { useId } from 'react'

/**
 * Account avatar: a person figure in the ZYNEX blue on a soft plate, with a presence light.
 * Figure from Microsoft Fluent UI System Icons ("person", MIT licence), recoloured.
 */
export default function UserAvatar({ size = 32, title }: { size?: number; title?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <span className="zx-avatar-plate" style={{ width: size, height: size }} title={title}>
      <svg width={size * 0.66} height={size * 0.66} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path fill={`url(#${id}b)`} d="M17.754 14a2.25 2.25 0 0 1 2.249 2.249v.918a2.75 2.75 0 0 1-.513 1.6C17.945 20.93 15.42 22 12 22s-5.944-1.072-7.486-3.236a2.75 2.75 0 0 1-.51-1.596v-.92A2.25 2.25 0 0 1 6.251 14z" />
        <path fill={`url(#${id}h)`} d="M12 2.005a5 5 0 1 1 0 10a5 5 0 0 1 0-10" />
        <defs>
          <linearGradient id={`${id}b`} x1="7.8" y1="15" x2="10.4" y2="23.3" gradientUnits="userSpaceOnUse">
            <stop offset=".12" stopColor="#4F86E0" /><stop offset="1" stopColor="#013D8C" />
          </linearGradient>
          <linearGradient id={`${id}h`} x1="9.4" y1="3.3" x2="14.5" y2="11.5" gradientUnits="userSpaceOnUse">
            <stop offset=".12" stopColor="#6E9BEA" /><stop offset="1" stopColor="#014BAA" />
          </linearGradient>
        </defs>
      </svg>
      <i className="zx-presence" aria-hidden="true" />
    </span>
  )
}
