import { useId, type CSSProperties } from 'react'

/**
 * The ZYNEX assistant icon: two overlapping speech bubbles with a typing indicator.
 * Shapes from Microsoft Fluent UI System Icons ("chat-multiple", MIT licence), recoloured in the ZYNEX palette:
 * brand blue for the front bubble, brand green for the reply behind it.
 */
export default function AssistantMark({ size = 16, className, style, title }: {
  size?: number; className?: string; style?: CSSProperties; title?: string
}) {
  const id = useId().replace(/:/g, '')
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}
      role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-label={title}>
      <path fill={`url(#${id}b)`} fillRule="evenodd" clipRule="evenodd"
        d="M22 13.5a7.5 7.5 0 1 0-4.411 6.836c1.258.29 2.613.54 3.236.652a.996.996 0 0 0 1.153-1.17a68 68 0 0 0-.681-3.143A7.5 7.5 0 0 0 22 13.5" />
      <path fill={`url(#${id}f)`} fillRule="evenodd" clipRule="evenodd"
        d="M2 10.5a7.5 7.5 0 1 1 4.411 6.836c-1.258.29-2.613.54-3.236.652a.996.996 0 0 1-1.153-1.17a68 68 0 0 1 .681-3.143A7.5 7.5 0 0 1 2 10.5" />
      <path fill={`url(#${id}s)`} fillOpacity="0.55" d="M9.5 3a7.5 7.5 0 0 1 7.47 6.82A7.5 7.5 0 0 0 10.4 17.95 7.5 7.5 0 0 1 9.5 3Z" />
      <circle cx="6.4" cy="10.5" r="1.15" fill="#fff" />
      <circle cx="9.5" cy="10.5" r="1.15" fill="#fff" fillOpacity="0.9" />
      <circle cx="12.6" cy="10.5" r="1.15" fill="#fff" fillOpacity="0.8" />
      <defs>
        <linearGradient id={`${id}f`} x1="2" y1="3" x2="17" y2="18" gradientUnits="userSpaceOnUse">
          <stop stopColor="#5B8FE6" /><stop offset="1" stopColor="#0A4BA8" />
        </linearGradient>
        <linearGradient id={`${id}b`} x1="10" y1="6" x2="22" y2="21" gradientUnits="userSpaceOnUse">
          <stop stopColor="#E3A46E" /><stop offset="1" stopColor="#B86A1E" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="9" y1="3" x2="12" y2="18" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0.35" /><stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  )
}
