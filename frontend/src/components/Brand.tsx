import { Link } from 'react-router'

export function LogoMark({ size = 40 }: { size?: number }) {
  const u = size / 40
  return (
    <span className="relative block shrink-0 bg-orange" style={{ width: size, height: size }} aria-hidden>
      <span className="absolute bg-white" style={{ bottom: 7 * u, left: 7 * u, width: 7 * u, height: 7 * u }} />
      <span className="absolute bg-white" style={{ bottom: 7 * u, left: 16 * u, width: 7 * u, height: 14 * u }} />
      <span className="absolute bg-white" style={{ bottom: 7 * u, left: 25 * u, width: 7 * u, height: 22 * u }} />
    </span>
  )
}

export function Wordmark({ to = '/', dark = true }: { to?: string; dark?: boolean }) {
  return (
    <Link to={to} className="flex items-center gap-3" aria-label="LeadRadar — pagina principală">
      <LogoMark />
      <span className="leading-none">
        <span className={`block text-[19px] font-bold ${dark ? 'text-white' : 'text-ink'}`}>LeadRadar</span>
        <span className={`mt-1 block text-[11px] font-bold ${dark ? 'text-orange' : 'text-orange-ink'}`}>Orange Systems</span>
      </span>
    </Link>
  )
}

/** Muted looping background video; shows the still frame when motion is reduced or the clip can't play. */
export function LoopVideo({ src, poster, className = '' }: { src: string; poster: string; className?: string }) {
  const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduce) return <img src={poster} alt="" className={`object-cover ${className}`} />
  return <video className={`object-cover ${className}`} src={src} poster={poster} autoPlay muted loop playsInline preload="auto" aria-hidden />
}
