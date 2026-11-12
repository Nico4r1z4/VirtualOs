// Formateo compacto de números y fechas para tableros densos.

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—"
  return Intl.NumberFormat("es", { notation: "compact", maximumFractionDigits: 1 }).format(n)
}

export function multiplier(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—"
  return `${x.toFixed(1)}×`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("es", { day: "2-digit", month: "short" })
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const diffMs = Date.now() - new Date(iso).getTime()
  const hours = Math.floor(diffMs / 3_600_000)
  if (hours < 1) return "hace minutos"
  if (hours < 24) return `hace ${hours} h`
  const days = Math.floor(hours / 24)
  return `hace ${days} d`
}
