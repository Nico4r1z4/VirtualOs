// Tablero de outliers: tabla densa con filtros, orden y drawer de detalle.

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink as LinkIcon, TrendingUp, X } from "lucide-react"
import { api, type OutlierFilters } from "@/api/client"
import { Badge, Card, EmptyState, ExternalLink, Spinner } from "@/components/ui"
import { compact, multiplier, relTime, shortDate } from "@/lib/format"

const MULTIPLIER_CHIPS = [1.5, 2, 3, 5, 10]
const PLATFORMS = [
  { value: "", label: "Todas" },
  { value: "tiktok", label: "TikTok" },
  { value: "instagram", label: "Instagram" },
]
const SORTS = [
  { value: "rank", label: "Ranking (recencia)" },
  { value: "outlier", label: "Multiplicador" },
  { value: "views", label: "Vistas" },
  { value: "velocity", label: "Velocidad" },
  { value: "recent", label: "Más recientes" },
] as const

function outlierColor(score: number | null): string {
  if (!score) return "#b0b8c4"
  if (score >= 10) return "#e74c3c"
  if (score >= 5) return "#f5a623"
  if (score >= 3) return "#3ec878"
  return "#1d9bf0"
}

export function OutliersPage() {
  const [filters, setFilters] = useState<OutlierFilters>({
    min_multiplier: 2,
    sort: "rank",
    page: 1,
    page_size: 25,
  })
  const [selected, setSelected] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ["outliers", filters],
    queryFn: () => api.outliers(filters),
  })

  const set = (patch: Partial<OutlierFilters>) =>
    setFilters((f) => ({ ...f, ...patch, page: patch.page ?? 1 }))

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="mb-1 text-2xl">Outliers</h1>
          <p className="text-sm text-gray-500">
            Contenido sobre-rindiendo vs. la mediana de cada autor
            {data ? ` · ${data.total} posts` : ""}
          </p>
        </div>
      </div>

      {/* Filtros */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-gray-200 bg-white p-0.5">
          {PLATFORMS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => set({ platform: p.value || undefined })}
              className={`cursor-pointer rounded-md px-3 py-1.5 text-xs font-bold transition-colors ${
                (filters.platform ?? "") === p.value
                  ? "bg-navy-800 text-white"
                  : "text-gray-500 hover:text-navy-800"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="label">Mín</span>
          {MULTIPLIER_CHIPS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => set({ min_multiplier: m })}
              className={`cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors ${
                filters.min_multiplier === m
                  ? "bg-blue-500 text-white"
                  : "bg-white text-gray-500 border border-gray-200 hover:border-blue-300"
              }`}
            >
              {m}×
            </button>
          ))}
        </div>

        <select
          value={filters.sort}
          onChange={(e) => set({ sort: e.target.value as OutlierFilters["sort"] })}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-bold text-gray-600 outline-none"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>

        <input
          type="date"
          value={filters.date_from?.slice(0, 10) ?? ""}
          onChange={(e) =>
            set({ date_from: e.target.value ? `${e.target.value}T00:00:00Z` : undefined })
          }
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 outline-none"
        />
        <span className="text-xs text-gray-400">→</span>
        <input
          type="date"
          value={filters.date_to?.slice(0, 10) ?? ""}
          onChange={(e) =>
            set({ date_to: e.target.value ? `${e.target.value}T23:59:59Z` : undefined })
          }
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 outline-none"
        />
      </div>

      {/* Tabla */}
      {isLoading ? (
        <Spinner />
      ) : error ? (
        <EmptyState title="Error cargando outliers" hint={(error as Error).message} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="Sin outliers con estos filtros"
          hint="Baja el multiplicador mínimo o espera a que termine la ingesta de tu nicho."
        />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left">
                <th className="label px-4 py-3">Post</th>
                <th className="label px-2 py-3 text-right">Outlier</th>
                <th className="label px-2 py-3 text-right">Vistas</th>
                <th className="label px-2 py-3 text-right">Likes</th>
                <th className="label px-2 py-3 text-right">Comparte</th>
                <th className="label px-2 py-3 text-right">Vel./h</th>
                <th className="label px-4 py-3 text-right">Publicado</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => setSelected(p.id)}
                  className="cursor-pointer border-b border-gray-50 transition-colors last:border-0 hover:bg-gray-50"
                >
                  <td className="max-w-md px-4 py-2.5">
                    <div className="flex items-center gap-3">
                      {p.thumbnail_url ? (
                        <img
                          src={p.thumbnail_url}
                          alt=""
                          className="h-12 w-9 shrink-0 rounded object-cover bg-gray-100"
                          loading="lazy"
                        />
                      ) : (
                        <div className="h-12 w-9 shrink-0 rounded bg-gray-100" />
                      )}
                      <div className="min-w-0">
                        <p className="truncate font-bold text-navy-800">
                          {p.caption || "(sin caption)"}
                        </p>
                        <p className="text-xs text-gray-400">
                          <Badge color={p.platform === "tiktok" ? "#1e2a38" : "#e1306c"}>
                            {p.platform}
                          </Badge>{" "}
                          @{p.author_handle ?? "?"}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2.5 text-right">
                    <span
                      className="rounded-full px-2 py-0.5 text-xs font-bold text-white"
                      style={{ backgroundColor: outlierColor(p.outlier_score) }}
                    >
                      {multiplier(p.outlier_score)}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 text-right font-bold">{compact(p.views)}</td>
                  <td className="px-2 py-2.5 text-right text-gray-500">{compact(p.likes)}</td>
                  <td className="px-2 py-2.5 text-right text-gray-500">{compact(p.shares)}</td>
                  <td className="px-2 py-2.5 text-right text-gray-500">
                    {p.velocity !== null && p.velocity > 0 ? (
                      <span className="inline-flex items-center gap-0.5 text-green-600">
                        <TrendingUp className="size-3" />
                        {compact(p.velocity)}
                      </span>
                    ) : (
                      compact(p.velocity)
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-gray-400">
                    {shortDate(p.published_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Paginación */}
          <div className="flex items-center justify-between border-t border-gray-100 px-4 py-2.5 text-xs text-gray-500">
            <span>
              Página {data.page} · {data.total} resultados
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={data.page <= 1}
                onClick={() => set({ page: (filters.page ?? 1) - 1 })}
                className="cursor-pointer rounded border border-gray-200 px-2 py-1 font-bold disabled:cursor-not-allowed disabled:opacity-40"
              >
                Anterior
              </button>
              <button
                type="button"
                disabled={data.page * data.page_size >= data.total}
                onClick={() => set({ page: (filters.page ?? 1) + 1 })}
                className="cursor-pointer rounded border border-gray-200 px-2 py-1 font-bold disabled:cursor-not-allowed disabled:opacity-40"
              >
                Siguiente
              </button>
            </div>
          </div>
        </Card>
      )}

      {selected && <PostDrawer postId={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function PostDrawer({ postId, onClose }: { postId: string; onClose: () => void }) {
  const { data: post, isLoading } = useQuery({
    queryKey: ["post", postId],
    queryFn: () => api.post(postId),
  })

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-navy-900/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg">Detalle del post</h2>
          <button type="button" onClick={onClose} className="cursor-pointer text-gray-400 hover:text-navy-800">
            <X className="size-5" />
          </button>
        </div>

        {isLoading || !post ? (
          <Spinner />
        ) : (
          <div className="flex flex-col gap-4 text-sm">
            <div className="flex items-start gap-3">
              {post.thumbnail_url && (
                <img src={post.thumbnail_url} alt="" className="w-24 rounded-lg bg-gray-100" />
              )}
              <div>
                <p className="font-bold">@{post.author_handle}</p>
                <p className="text-xs text-gray-500">
                  {post.platform} · {shortDate(post.published_at)} · {relTime(post.published_at)}
                </p>
                {post.url && (
                  <ExternalLink href={post.url}>
                    <span className="inline-flex items-center gap-1 text-xs">
                      Ver post <LinkIcon className="size-3" />
                    </span>
                  </ExternalLink>
                )}
              </div>
            </div>

            <p className="whitespace-pre-wrap text-gray-700">{post.caption}</p>

            <div className="grid grid-cols-2 gap-2">
              <Stat label="Multiplicador" value={multiplier(post.outlier_score)} highlight />
              <Stat label="Vistas" value={compact(post.views)} />
              <Stat label="Likes" value={compact(post.likes)} />
              <Stat label="Comentarios" value={compact(post.comments)} />
              <Stat label="Compartidos" value={compact(post.shares)} />
              <Stat
                label="Velocidad"
                value={post.velocity !== null ? `${compact(post.velocity)}/h` : "—"}
              />
            </div>

            {post.sound_name && (
              <div>
                <p className="label mb-1">Sonido</p>
                <p className="text-gray-700">{post.sound_name}</p>
              </div>
            )}

            {post.hashtags.length > 0 && (
              <div>
                <p className="label mb-1.5">Hashtags</p>
                <div className="flex flex-wrap gap-1.5">
                  {post.hashtags.map((h) => (
                    <span key={h} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                      #{h}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {post.hook && (
              <div className="rounded-lg bg-blue-100/60 p-3">
                <p className="label mb-1">Gancho detectado</p>
                <p className="font-bold text-navy-800">{post.hook.hook_text}</p>
                {post.hook.cta && <p className="mt-1 text-xs text-gray-600">CTA: {post.hook.cta}</p>}
              </div>
            )}

            {post.snapshots.length > 1 && (
              <div>
                <p className="label mb-1.5">Evolución de vistas</p>
                <div className="flex flex-col gap-1 text-xs text-gray-500">
                  {post.snapshots.slice(-6).map((s) => (
                    <div key={s.captured_at} className="flex justify-between">
                      <span>{new Date(s.captured_at).toLocaleString("es")}</span>
                      <span className="font-bold text-navy-800">{compact(s.views)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-lg p-2.5 ${highlight ? "bg-blue-100" : "bg-gray-50"}`}>
      <p className="label text-[10px]">{label}</p>
      <p className={`text-base font-bold ${highlight ? "text-blue-600" : "text-navy-800"}`}>{value}</p>
    </div>
  )
}
