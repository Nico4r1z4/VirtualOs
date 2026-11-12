// Componentes base del dashboard, estilo shadcn pero hechos a mano sobre los
// tokens Orkiza. Suficientes para 6 pantallas; sin dependencias extra.

import { useEffect, useState, type ReactNode } from "react"

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl bg-white shadow-sm border border-gray-100 ${className}`}>
      {children}
    </div>
  )
}

export function Badge({
  color,
  children,
  pulse = false,
}: {
  color: string
  children: ReactNode
  pulse?: boolean
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ${pulse ? "hitl-pulse" : ""}`}
      style={{ backgroundColor: `${color}22`, color: adjustForText(color) }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {children}
    </span>
  )
}

// Colores muy claros de la paleta no legibles como texto → oscurece al tono hermano.
function adjustForText(color: string): string {
  const map: Record<string, string> = {
    "#8ed0f9": "#0e7fcf",
    "#b0b8c4": "#637180",
    "#8896a5": "#475767",
    "#3ec878": "#3ab369",
  }
  return map[color] ?? color
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled = false,
  type = "button",
}: {
  children: ReactNode
  onClick?: () => void
  variant?: "primary" | "ghost" | "success" | "danger"
  disabled?: boolean
  type?: "button" | "submit"
}) {
  const styles: Record<string, string> = {
    primary: "bg-blue-500 text-white hover:bg-blue-600",
    ghost: "bg-transparent text-navy-800 border border-gray-200 hover:bg-gray-100",
    success: "bg-green-500 text-white hover:bg-green-600",
    danger: "bg-error text-white hover:opacity-90",
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${styles[variant]}`}
    >
      {children}
    </button>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-12 text-gray-400">
      <div className="size-6 animate-spin rounded-full border-2 border-gray-200 border-t-blue-500" />
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 p-12 text-center">
      <p className="font-bold text-gray-500">{title}</p>
      {hint && <p className="text-sm text-gray-400">{hint}</p>}
    </div>
  )
}

// Toast mínimo: un solo mensaje a la vez, se autodescarta.
let pushToast: ((msg: string, kind: "info" | "error") => void) | null = null

export function toast(msg: string, kind: "info" | "error" = "info") {
  pushToast?.(msg, kind)
}

export function Toaster() {
  const [current, setCurrent] = useState<{ msg: string; kind: "info" | "error" } | null>(null)

  useEffect(() => {
    pushToast = (msg, kind) => setCurrent({ msg, kind })
    return () => {
      pushToast = null
    }
  }, [])

  useEffect(() => {
    if (!current) return
    const t = setTimeout(() => setCurrent(null), 4500)
    return () => clearTimeout(t)
  }, [current])

  if (!current) return null
  return (
    <div
      className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg px-5 py-3 text-sm font-bold text-white shadow-lg"
      style={{ backgroundColor: current.kind === "error" ? "#e74c3c" : "#1e2a38" }}
    >
      {current.msg}
    </div>
  )
}

/** Payload no confiable (scrapeado): SIEMPRE texto plano, nunca HTML. */
export function PlainPayload({ data }: { data: unknown }) {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2)
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-100 p-3 font-mono text-xs text-gray-700">
      {text}
    </pre>
  )
}

/** Link externo a sitio scrapeado: sin embeds, noopener siempre. */
export function ExternalLink({ href, children }: { href: string; children?: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-500 hover:underline break-all"
    >
      {children ?? href}
    </a>
  )
}
