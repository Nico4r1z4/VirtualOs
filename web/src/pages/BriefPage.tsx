// Brief semanal: plan de grabación con cada idea enlazada a su evidencia.

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarRange, Check, Download, FileText, Loader2 } from "lucide-react"
import { api, get, post } from "@/api/client"
import { useActiveJob } from "@/components/JobsBar"
import { supabase } from "@/lib/supabase"
import { Badge, Button, Card, EmptyState, ExternalLink, Spinner, toast } from "@/components/ui"
import { compact, multiplier, shortDate } from "@/lib/format"

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000"

type BriefSummary = {
  id: string
  week_start: string
  summary: string | null
  created_at: string
  niche_name: string | null
  idea_count: number
}

type Idea = {
  id: string
  title: string
  angle: string | null
  hook_suggestion: string | null
  script_outline: string | null
  status: string
  evidence_post_ids: string[]
  evidence_trend_ids: string[]
  evidence_news_ids: string[]
  feedback_count: number
}

type BriefDetail = BriefSummary & {
  content: { plan?: { day: string; idea_id: string }[] }
  ideas: Idea[]
  evidence: {
    posts: Record<string, { author_handle: string; caption: string; views: number; outlier_score: number; url: string | null; platform: string }>
    trends: Record<string, { name: string; country: string; rank: number | null }>
    news: Record<string, { title: string; url: string; source: string | null }>
  }
}

export function BriefPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: briefs, isLoading } = useQuery({
    queryKey: ["briefs"],
    queryFn: () => get<{ items: BriefSummary[] }>("/briefs"),
  })

  const running = useActiveJob("build_weekly_brief")
  const generate = useMutation({
    mutationFn: api.generateBrief,
    onSuccess: (res) => {
      toast(
        res.status === "already_running"
          ? "Ya se está generando un brief: no se lanzó otro ni se cobró de nuevo."
          : "Generando tu brief. Mira el avance arriba; te avisamos al terminar.",
      )
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
    onError: (e) => toast((e as Error).message, "error"),
  })
  const busy = generate.isPending || !!running

  const activeId = selectedId ?? briefs?.items[0]?.id ?? null

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="mb-1 text-2xl">Brief semanal</h1>
          <p className="text-sm text-gray-500">
            Tu plan de grabación, cada idea anclada a evidencia real del nicho
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button onClick={() => generate.mutate()} disabled={busy}>
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <CalendarRange className="size-4" />
            )}
            {busy ? "Generando…" : "Generar brief de la semana"}
          </Button>
          <span className="text-[11px] text-gray-400">
            Analiza antes los ganchos que falten · ~US$0.04 por brief
          </span>
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : !briefs || briefs.items.length === 0 ? (
        <EmptyState
          title="Todavía no hay briefs"
          hint="Genera el primero cuando el tablero de outliers tenga datos y ganchos."
        />
      ) : (
        <div className="flex gap-4">
          <div className="flex w-52 shrink-0 flex-col gap-2">
            {briefs.items.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setSelectedId(b.id)}
                className={`cursor-pointer rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  activeId === b.id
                    ? "border-blue-400 bg-blue-100/60"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <p className="font-bold text-navy-800">Semana {shortDate(b.week_start)}</p>
                <p className="text-gray-500">
                  {b.niche_name ?? "nicho"} · {b.idea_count} ideas
                </p>
              </button>
            ))}
          </div>
          <div className="min-w-0 flex-1">
            {activeId && <BriefDetailView briefId={activeId} />}
          </div>
        </div>
      )}
    </div>
  )
}

function BriefDetailView({ briefId }: { briefId: string }) {
  const qc = useQueryClient()
  const { data: brief, isLoading } = useQuery({
    queryKey: ["brief", briefId],
    queryFn: () => get<BriefDetail>(`/briefs/${briefId}`),
  })

  const feedback = useMutation({
    mutationFn: (ideaId: string) => post(`/ideas/${ideaId}/feedback`, { recorded: true }),
    onSuccess: () => {
      toast("Registrado: idea marcada como grabada 🎬")
      qc.invalidateQueries({ queryKey: ["brief", briefId] })
    },
    onError: (e) => toast((e as Error).message, "error"),
  })

  async function downloadPdf() {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const res = await fetch(`${API_BASE}/briefs/${briefId}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      toast("No se pudo generar el PDF", "error")
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `brief-${brief?.week_start ?? "semana"}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading || !brief) return <Spinner />

  const dayFor = new Map((brief.content.plan ?? []).map((p) => [p.idea_id, p.day]))

  return (
    <div className="flex flex-col gap-4">
      {brief.summary && (
        <Card className="p-4">
          <div className="mb-1 flex items-center justify-between">
            <p className="label">Qué está funcionando</p>
            <Button variant="ghost" onClick={downloadPdf}>
              <Download className="size-3.5" />
              PDF
            </Button>
          </div>
          <p className="text-sm text-gray-700">{brief.summary}</p>
        </Card>
      )}

      {brief.ideas.map((idea) => (
        <Card key={idea.id} className="p-4">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              {dayFor.get(idea.id) && (
                <p className="label mb-0.5 text-blue-600">{dayFor.get(idea.id)}</p>
              )}
              <h3 className="text-base">{idea.title}</h3>
            </div>
            {idea.status === "recorded" || idea.feedback_count > 0 ? (
              <Badge color="#3ec878">grabada</Badge>
            ) : (
              <Button variant="success" onClick={() => feedback.mutate(idea.id)}>
                <Check className="size-3.5" />
                Lo grabé
              </Button>
            )}
          </div>

          {idea.hook_suggestion && (
            <p className="mb-2 rounded-lg bg-blue-100/60 p-2.5 text-sm font-bold text-navy-800">
              “{idea.hook_suggestion}”
            </p>
          )}
          {idea.angle && <p className="mb-2 text-sm text-gray-600">{idea.angle}</p>}
          {idea.script_outline && (
            <pre className="mb-3 whitespace-pre-wrap rounded-lg bg-gray-50 p-2.5 font-body text-xs text-gray-600">
              {idea.script_outline}
            </pre>
          )}

          {/* Evidencia */}
          <div className="border-t border-gray-100 pt-2">
            <p className="label mb-1.5 flex items-center gap-1">
              <FileText className="size-3" />
              Evidencia
            </p>
            <div className="flex flex-col gap-1 text-xs">
              {idea.evidence_post_ids.map((pid) => {
                const p = brief.evidence.posts[pid]
                if (!p) return null
                return (
                  <div key={pid} className="flex items-center gap-2 text-gray-600">
                    <Badge color="#1d9bf0">post</Badge>
                    <span className="truncate">
                      @{p.author_handle} · {multiplier(p.outlier_score)} · {compact(p.views)} vistas
                    </span>
                    {p.url && <ExternalLink href={p.url}>ver</ExternalLink>}
                  </div>
                )
              })}
              {idea.evidence_trend_ids.map((tid) => {
                const t = brief.evidence.trends[tid]
                if (!t) return null
                return (
                  <div key={tid} className="flex items-center gap-2 text-gray-600">
                    <Badge color="#00b09b">tendencia</Badge>
                    <span>
                      #{t.name} ({t.country})
                    </span>
                  </div>
                )
              })}
              {idea.evidence_news_ids.map((nid) => {
                const n = brief.evidence.news[nid]
                if (!n) return null
                return (
                  <div key={nid} className="flex items-center gap-2 text-gray-600">
                    <Badge color="#f5a623">noticia</Badge>
                    <span className="truncate">{n.title}</span>
                    <ExternalLink href={n.url}>ver</ExternalLink>
                  </div>
                )
              })}
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}
