/** Color math for palette checks (viz-style-guide → How to check a palette change). */

type RGB = [number, number, number]

const toLinear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)

export function hexToLinear(hex: string): RGB {
  return [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255)) as RGB
}

/** Linear sRGB → OKLab (Björn Ottosson). */
export function linearToOklab([r, g, b]: RGB): RGB {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

export const oklab = (hex: string) => linearToOklab(hexToLinear(hex))

export function oklch(hex: string): { l: number; c: number; h: number } {
  const [l, a, b] = oklab(hex)
  return { l, c: Math.hypot(a, b), h: ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360 }
}

const dist = (x: RGB, y: RGB) => 100 * Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2])

/** OKLab ΔE × 100. */
export const deltaE = (a: string, b: string) => dist(oklab(a), oklab(b))

/** Machado et al. 2009 simulation matrices, severity 1.0, applied in linear RGB. */
const MACHADO = {
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
} as const

export type Deficiency = keyof typeof MACHADO

export function deltaECvd(a: string, b: string, kind: Deficiency): number {
  const sim = (hex: string): RGB => {
    const c = hexToLinear(hex)
    return MACHADO[kind].map((row) => Math.min(1, Math.max(0, row[0] * c[0] + row[1] * c[1] + row[2] * c[2]))) as RGB
  }
  return dist(linearToOklab(sim(a)), linearToOklab(sim(b)))
}

/** WCAG 2 contrast ratio. */
export function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = hexToLinear(hex)
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
