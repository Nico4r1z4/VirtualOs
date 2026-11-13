// Barra global de procesos en curso (ingesta, ganchos, brief).
// Muestra qué está pasando con los datos, el avance y el tiempo transcurrido,
// avisa al terminar y refresca las vistas. Los botones la consultan con
// useActiveJob() para no lanzar dos veces un proceso que cuesta dinero.

import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Loader2, XCircle } from "lucide-react"
import { api, type JobInfo } from "@/api/client"
import { toast } from "@/components/ui"

export const JOB_LABELS: Record<string, string> = {
  ingest_niche: "Ingesta de datos del nicho",
  refresh_news: "Actualización de noticias",
  synthesize_hooks: "Análisis de ganchos",
  build_weekly_brief: "Brief semanal",
}

// Expectativa honesta de duración, para que la espera no se sienta vacía.
const JOB_ETA: Record<string, string> = {
  ingest_niche: "suele tardar 3–6 min",
  refresh_news: "suele tardar unos segundos",
  synthesize_hooks: "~30 s por outlier",
  build_weekly_brief: "suele tardar 1–2 min",
}

const isActive = (j: JobInfo) => j.status === "pending" || j.status === "running"

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    // Rápido mientras hay algo corriendo; lento en reposo (detecta jobs que
    // lance la mascota sin que el usuario pulse nada).
    refetchInterval: (q) => (q.state.data?.items.some(isActive) ? 2500 : 10000),
  })
}

export function useActiveJob(kind: string): JobInfo | undefined {
  const { data } = useJobs()
  return data?.items.find((j) => j.kind === kind && isActive(j))
}

function elapsed(fromIso: string | null, now: number): string {
  if (!fromIso) return ""
  const s = Math.max(0, Math.floor((now - new Date(fromIso).getTime()) / 1000))
  const m = Math.floor(s / 60)
  return m > 0 ? `${m} min ${String(s % 60).padStart(2, "0")} s` : `${s} s`
}

function resultSummary(job: JobInfo): string {
  const r = (job.progress?.result ?? {}) as Record<string, unknown>
  switch (job.kind) {
    case "ingest_niche":
      return `${r.posts ?? 0} posts, ${r.trends ?? 0} tendencias, ${r.news ?? 0} noticias`
    case "refresh_news":
      return `${r.news ?? 0} noticias nuevas`
    case "synthesize_hooks":
      return `${r.hooks_created ?? 0} ganchos nuevos`
    case "build_weekly_brief":
      return `${r.ideas_kept ?? 0} ideas con evidencia`
    default:
      return ""
  }
}

export function JobsBar() {
  const qc = useQueryClient()
  const { data } = useJobs()
  const [now, setNow] = useState(() => Date.now())
  const seenActive = useRef<Set<string>>(new Set())

  const active = data?.items.filter(isActive) ?? []

  // Reloj para el tiempo transcurrido, solo mientras hay algo corriendo.
  useEffect(() => {
    if (active.length === 0) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active.length])

  // Detecta transiciones activo -> terminado: avisa y refresca las vistas.
  useEffect(() => {
    if (!data) return
    for (const job of data.items) {
      if (isActive(job)) {
        seenActive.current.add(job.id)
      } else if (seenActive.current.has(job.id)) {
        seenActive.current.delete(job.id)
        const label = JOB_LABELS[job.kind] ?? job.kind
        if (job.status === "done") {
          toast(`✅ ${label} listo: ${resultSummary(job)}`)
        } else {
          toast(`${label} falló. Puedes reintentarlo.`, "error")
        }
        qc.invalidateQueries()
      }
    }
  }, [data, qc])

  if (active.length === 0) return null

  return (
    <div className="mb-6 flex flex-col gap-2">
      {active.map((job) => {
        const p = job.progress ?? {}
        const hasTotal = typeof p.total === "number" && p.total > 0
        const pct = hasTotal ? Math.round(((p.done ?? 0) / (p.total as number)) * 100) : null
        return (
          <div
            key={job.id}
            className="rounded-xl border border-blue-300/60 bg-blue-100/50 px-4 py-3"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-center gap-3">
              <Loader2 className="size-4 shrink-0 animate-spin text-blue-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-navy-800">
                  {JOB_LABELS[job.kind] ?? job.kind}
                  <span className="ml-2 font-normal text-gray-500">
                    {job.status === "pending" ? "en cola…" : p.stage ?? "en curso…"}
                    {hasTotal && ` · ${p.done ?? 0}/${p.total}`}
                  </span>
                </p>
                <p className="text-xs text-gray-500">
                  {job.status === "running" && `${elapsed(job.started_at, now)} · `}
                  {JOB_ETA[job.kind]} · puedes seguir navegando, te avisamos al terminar
                </p>
              </div>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white">
              {pct !== null ? (
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.max(pct, 4)}%` }}
                />
              ) : (
                <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-400" />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function JobStatusIcon({ job }: { job: JobInfo }) {
  if (isActive(job)) return <Loader2 className="size-3.5 animate-spin" />
  if (job.status === "done") return <CheckCircle2 className="size-3.5 text-green-600" />
  return <XCircle className="size-3.5 text-error" />
}
