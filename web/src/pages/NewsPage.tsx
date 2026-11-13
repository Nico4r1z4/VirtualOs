// Noticias del nicho: medios nacionales + Google News, las más nuevas primero.
// La promesa es "enterarte primero": recencia visible y marca de lo de hoy.

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Newspaper, RefreshCw, Search } from "lucide-react"
import { api, type NewsItem } from "@/api/client"
import { useActiveJob } from "@/components/JobsBar"
import { Badge, Button, Card, EmptyState, ExternalLink, Spinner, toast } from "@/components/ui"
import { relTime } from "@/lib/format"

const DAY_MS = 24 * 3600 * 1000

function isFresh(n: NewsItem): boolean {
  const t = n.published_at ?? n.created_at
  return !!t && Date.now() - new Date(t).getTime() < DAY_MS
}

export function NewsPage() {
  const [q, setQ] = useState("")
  const [query, setQuery] = useState("")
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["news", query],
    queryFn: () => api.news(query || undefined),
  })

  const running = useActiveJob("refresh_news")
  const refresh = useMutation({
    mutationFn: api.refreshNews,
    onSuccess: (res) => {
      toast(
        res.status === "already_running"
          ? "Ya se están actualizando las noticias."
          : "Buscando noticias nuevas en medios y Google News…",
      )
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
    onError: (e) => toast((e as Error).message, "error"),
  })
  const busy = refresh.isPending || !!running

  const items = data?.items ?? []
  const freshCount = items.filter(isFresh).length

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="mb-1 text-2xl">Noticias del nicho</h1>
          <p className="text-sm text-gray-500">
            Medios nacionales y Google News filtrados por tus keywords, lo más reciente primero
            {items.length > 0 && ` · ${freshCount} de las últimas 24 h`}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button onClick={() => refresh.mutate()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            {busy ? "Actualizando…" : "Actualizar noticias"}
          </Button>
          <span className="text-[11px] text-gray-400">Gratis · no usa scraping pago</span>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(q.trim())
        }}
        className="mb-4 flex max-w-md items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5"
      >
        <Search className="size-4 text-gray-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar en las noticias (ej. tasas, ahorro)"
          className="min-w-0 flex-1 text-sm outline-none"
        />
      </form>

      {isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState
          title={query ? `Sin noticias que mencionen "${query}"` : "Todavía no hay noticias"}
          hint='Pulsa "Actualizar noticias": tarda unos segundos y es gratis.'
        />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((n) => (
            <Card key={n.id} className="p-4">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                {isFresh(n) && <Badge color="#3ec878">Nuevo</Badge>}
                <span className="font-bold text-navy-800">{n.source ?? "Medio"}</span>
                <span>· {relTime(n.published_at ?? n.created_at)}</span>
                {n.origin === "gnews" && (
                  <span className="inline-flex items-center gap-1 text-gray-400">
                    · <Newspaper className="size-3" /> Google News
                  </span>
                )}
              </div>
              <ExternalLink href={n.url}>
                <span className="font-display text-base font-bold text-navy-800 hover:text-blue-600">
                  {n.title}
                </span>
              </ExternalLink>
              {n.snippet && (
                <p className="mt-1 line-clamp-2 text-sm text-gray-600">{n.snippet}</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
