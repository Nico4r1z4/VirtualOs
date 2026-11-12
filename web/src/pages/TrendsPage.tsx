// Radar de tendencias de plataforma por país (hashtags y sonidos).

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { Card, EmptyState, Spinner } from "@/components/ui"
import { compact } from "@/lib/format"

const COUNTRIES = ["CO", "MX", "AR", "PE", "CL", "US", "ES"]

export function TrendsPage() {
  const [country, setCountry] = useState("CO")

  const { data, isLoading } = useQuery({
    queryKey: ["trends", country],
    queryFn: () => api.trends("tiktok", country),
  })

  const hashtags = data?.items.filter((t) => t.trend_type === "hashtag") ?? []
  const sounds = data?.items.filter((t) => t.trend_type === "sound") ?? []

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-1 text-2xl">Tendencias</h1>
        <p className="text-sm text-gray-500">Hashtags y sonidos trending de TikTok por país</p>
      </div>

      <div className="mb-4 flex gap-1.5">
        {COUNTRIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCountry(c)}
            className={`cursor-pointer rounded-full px-3 py-1 text-xs font-bold transition-colors ${
              country === c
                ? "bg-navy-800 text-white"
                : "bg-white text-gray-500 border border-gray-200 hover:border-gray-300"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title={`Sin tendencias para ${country}`}
          hint="Las tendencias se capturan con cada ingesta de tu nicho."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="p-4">
            <p className="label mb-3">Hashtags</p>
            <div className="flex flex-col gap-1">
              {hashtags.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-gray-50"
                >
                  <div className="flex items-center gap-3">
                    <span className="w-6 text-right text-xs font-bold text-gray-400">
                      {t.rank ?? "·"}
                    </span>
                    <span className="font-bold text-navy-800">#{t.name}</span>
                  </div>
                  <span className="text-xs text-gray-500">
                    {t.metrics.videoViews !== undefined
                      ? `${compact(Number(t.metrics.videoViews))} vistas`
                      : t.metrics.publishCnt !== undefined
                        ? `${compact(Number(t.metrics.publishCnt))} posts`
                        : ""}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <p className="label mb-3">Sonidos</p>
            {sounds.length === 0 ? (
              <p className="p-3 text-sm text-gray-400">
                Sin sonidos capturados aún para este país.
              </p>
            ) : (
              <div className="flex flex-col gap-1">
                {sounds.map((t) => (
                  <div key={t.id} className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-gray-50">
                    <span className="font-bold text-navy-800">{t.name}</span>
                    <span className="text-xs text-gray-400">{t.rank ?? ""}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
