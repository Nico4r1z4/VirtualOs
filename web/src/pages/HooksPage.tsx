// Biblioteca de ganchos: qué capturó atención en los posts que ganaron.

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Sparkles } from "lucide-react"
import { api, get } from "@/api/client"
import { useActiveJob } from "@/components/JobsBar"
import { Badge, Button, Card, EmptyState, ExternalLink, Spinner, toast } from "@/components/ui"
import { compact, multiplier } from "@/lib/format"

type Hook = {
  id: string
  post_id: string
  hook_text: string
  hook_type: string | null
  structure: { formato?: string; beats?: string[]; duracion_estimada_s?: number }
  cta: string | null
  language: string | null
  platform: string
  author_handle: string | null
  caption: string | null
  views: number | null
  outlier_score: number | null
  thumbnail_url: string | null
  url: string | null
}

const TYPE_COLORS: Record<string, string> = {
  pregunta: "#1d9bf0",
  dato_impactante: "#e74c3c",
  historia: "#00b09b",
  controversia: "#f5a623",
  lista: "#3ec878",
  tutorial: "#2e4060",
  reto: "#e1306c",
  otro: "#8896a5",
}

const TYPES = ["", "pregunta", "dato_impactante", "historia", "controversia", "lista", "tutorial", "reto"]

export function HooksPage() {
  const [hookType, setHookType] = useState("")
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["hooks", hookType],
    queryFn: () =>
      get<{ items: Hook[] }>(`/hooks${hookType ? `?hook_type=${hookType}` : ""}`),
  })

  const running = useActiveJob("synthesize_hooks")
  const synthesize = useMutation({
    mutationFn: api.synthesizeHooks,
    onSuccess: (res) => {
      toast(
        res.status === "already_running"
          ? "Ya hay un análisis en curso: no se lanzó otro ni se cobró de nuevo."
          : "Analizando ganchos. Mira el avance arriba; te avisamos al terminar.",
      )
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
    onError: (e) => toast((e as Error).message, "error"),
  })
  const busy = synthesize.isPending || !!running

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="mb-1 text-2xl">Biblioteca de ganchos</h1>
          <p className="text-sm text-gray-500">
            Ganchos y estructuras extraídos solo de los posts que sobre-rindieron
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button onClick={() => synthesize.mutate()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {busy ? "Analizando…" : "Analizar outliers nuevos"}
          </Button>
          <span className="text-[11px] text-gray-400">
            Solo procesa outliers sin analizar · ~US$0.002 c/u
          </span>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setHookType(t)}
            className={`cursor-pointer rounded-full px-3 py-1 text-xs font-bold transition-colors ${
              hookType === t
                ? "bg-navy-800 text-white"
                : "bg-white text-gray-500 border border-gray-200 hover:border-gray-300"
            }`}
          >
            {t === "" ? "Todos" : t.replace("_", " ")}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="Sin ganchos todavía"
          hint='Pulsa "Analizar outliers nuevos" cuando el tablero tenga datos.'
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {data.items.map((h) => (
            <Card key={h.id} className="flex flex-col p-4">
              <div className="mb-2 flex items-center justify-between">
                <Badge color={TYPE_COLORS[h.hook_type ?? "otro"] ?? "#8896a5"}>
                  {(h.hook_type ?? "otro").replace("_", " ")}
                </Badge>
                <span className="text-xs font-bold text-gray-400">
                  {multiplier(h.outlier_score)} · {compact(h.views)} vistas
                </span>
              </div>
              <p className="mb-3 font-display text-base font-bold text-navy-800">
                “{h.hook_text}”
              </p>
              {h.structure?.beats && h.structure.beats.length > 0 && (
                <ol className="mb-3 flex flex-col gap-1 text-xs text-gray-600">
                  {h.structure.beats.slice(0, 5).map((b, i) => (
                    <li key={b} className="flex gap-2">
                      <span className="font-bold text-blue-500">{i + 1}.</span>
                      {b}
                    </li>
                  ))}
                </ol>
              )}
              {h.cta && (
                <p className="mb-3 text-xs text-gray-500">
                  <b>CTA:</b> {h.cta}
                </p>
              )}
              <div className="mt-auto flex items-center justify-between border-t border-gray-100 pt-2 text-xs text-gray-400">
                <span>
                  {h.platform} · @{h.author_handle}
                </span>
                {h.url && <ExternalLink href={h.url}>ver post</ExternalLink>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
