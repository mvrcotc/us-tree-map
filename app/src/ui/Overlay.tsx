/**
 * Vignette (darkness ≤ 0.35, frame edge only) and grain (≤ 3% opacity) as one CSS overlay over
 * both layers (viz-style-guide → Stage → Effects). `?grain=0` turns grain off for color tests.
 */
const NOISE =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")"

export function Overlay() {
  const grain = new URLSearchParams(location.search).get('grain') !== '0'
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse at center, transparent 62%, rgba(20, 28, 38, 0.3) 100%)' }} />
      {grain && <div className="absolute inset-0 opacity-[0.03] mix-blend-multiply" style={{ backgroundImage: NOISE }} />}
    </div>
  )
}
