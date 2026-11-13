// Panel lateral de la mascota: chat SSE con tarjetas de acciones ejecutadas.
// La mascota opera las herramientas; no reemplaza la UI.

import { useEffect, useRef, useState } from "react"
import { Bot, ChevronRight, Loader2, Send, Wrench } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { supabase } from "@/lib/supabase"
import { get } from "@/api/client"

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000"

type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; name: string; summary: string }
  | { kind: "error"; text: string }

const TOOL_LABELS: Record<string, string> = {
  upsert_niche_profile: "Guardando perfil de nicho",
  start_ingestion: "Lanzando ingesta de datos",
  get_job_status: "Consultando estado del job",
  get_outliers: "Consultando outliers",
  get_platform_trends: "Consultando tendencias",
  get_hooks: "Consultando ganchos",
  build_weekly_brief: "Encolando brief semanal",
  explain_feature: "Buscando explicación",
}

function summarizeResult(name: string, result: Record<string, unknown>): string {
  if (result.error) return `Error: ${String(result.detail ?? result.error)}`
  switch (name) {
    case "upsert_niche_profile":
      return `Perfil "${String(result.name)}" ${result.created ? "creado" : "actualizado"}`
    case "start_ingestion":
    case "build_weekly_brief":
      return `Job encolado (${String(result.job_id).slice(0, 8)}…)`
    case "get_job_status":
      return `Estado: ${String(result.status)}`
    case "get_outliers":
    case "get_platform_trends":
    case "get_hooks":
      return `${String(result.count)} resultados`
    default:
      return "Listo"
  }
}

export function MascotPanel({ startOpen = false }: { startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen)
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const conversationRef = useRef<string | null>(null)
  const storageKeyRef = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const qc = useQueryClient()

  // Only ever OPEN automatically (onboarding); never close or reset on
  // re-render — the panel must survive the profile being created mid-chat.
  useEffect(() => {
    if (startOpen) setOpen(true)
  }, [startOpen])

  // Restore this user's last conversation from the server after a reload.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data } = await supabase.auth.getSession()
      const userId = data.session?.user.id
      if (!userId) return
      const key = `vos_conversation_${userId}`
      storageKeyRef.current = key
      let saved: string | null = null
      try {
        saved = localStorage.getItem(key)
      } catch {
        return
      }
      if (!saved) return
      try {
        const res = await get<{ items: { role: string; content: string | null }[] }>(
          `/agent/conversations/${saved}/messages`,
        )
        if (cancelled) return
        conversationRef.current = saved
        setItems(
          res.items
            .filter((m) => m.content && (m.role === "user" || m.role === "assistant"))
            .map((m) =>
              m.role === "user"
                ? { kind: "user" as const, text: m.content as string }
                : { kind: "assistant" as const, text: m.content as string },
            ),
        )
      } catch {
        // Conversation gone or belongs to another workspace: start fresh.
        try {
          localStorage.removeItem(key)
        } catch {
          /* storage unavailable */
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  function rememberConversation(id: string) {
    conversationRef.current = id
    const key = storageKeyRef.current
    if (!key) return
    try {
      localStorage.setItem(key, id)
    } catch {
      /* storage unavailable: conversation still works for this page view */
    }
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [items])

  async function send() {
    const message = input.trim()
    if (!message || busy) return
    setInput("")
    setItems((xs) => [...xs, { kind: "user", text: message }])
    setBusy(true)

    try {
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token
      const res = await fetch(`${API_BASE}/agent/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message, conversation_id: conversationRef.current }),
      })
      if (!res.ok || !res.body) {
        const detail = await res.text()
        setItems((xs) => [...xs, { kind: "error", text: detail || `Error ${res.status}` }])
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let eventName = ""

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim()
          } else if (line.startsWith("data:")) {
            const payload = JSON.parse(line.slice(5).trim()) as Record<string, unknown>
            if (eventName === "meta") {
              rememberConversation(String(payload.conversation_id))
            } else if (eventName === "text") {
              setItems((xs) => [...xs, { kind: "assistant", text: String(payload.content) }])
            } else if (eventName === "tool_result") {
              const name = String(payload.name)
              setItems((xs) => [
                ...xs,
                {
                  kind: "tool",
                  name: TOOL_LABELS[name] ?? name,
                  summary: summarizeResult(name, (payload.result ?? {}) as Record<string, unknown>),
                },
              ])
              // Refresca las vistas que la mascota pudo haber cambiado.
              qc.invalidateQueries()
            } else if (eventName === "error") {
              setItems((xs) => [...xs, { kind: "error", text: String(payload.detail) }])
            }
          }
        }
      }
    } catch (e) {
      setItems((xs) => [...xs, { kind: "error", text: (e as Error).message }])
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="soft-pulse fixed bottom-6 right-6 z-30 flex cursor-pointer items-center gap-2 rounded-full bg-navy-800 px-4 py-3 font-bold text-white shadow-lg transition-transform hover:scale-105"
      >
        <Bot className="size-5" />
        Mascota
      </button>
    )
  }

  return (
    <aside className="fixed bottom-0 right-0 top-0 z-30 flex w-96 flex-col border-l border-gray-200 bg-white shadow-lg">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-blue-100">
            <Bot className="size-4 text-blue-600" />
          </div>
          <div>
            <p className="text-sm font-bold text-navy-800">Mascota VirtualOS</p>
            <p className="text-[10px] text-gray-400">Todo número sale de una herramienta</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="cursor-pointer text-gray-400 hover:text-navy-800"
        >
          <ChevronRight className="size-5" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3">
        {items.length === 0 && (
          <div className="mt-8 text-center text-sm text-gray-400">
            <Bot className="mx-auto mb-2 size-8" />
            <p className="font-bold text-gray-500">¡Hola! Soy tu copiloto de contenido.</p>
            <p className="mt-1">
              Si aún no tienes perfil de nicho, dime de qué va tu contenido y lo armamos juntos.
            </p>
          </div>
        )}
        <div className="flex flex-col gap-2.5">
          {items.map((item, i) => {
            if (item.kind === "user")
              return (
                <div key={i} className="ml-8 rounded-2xl rounded-br-sm bg-navy-800 px-3 py-2 text-sm text-white">
                  {item.text}
                </div>
              )
            if (item.kind === "assistant")
              return (
                <div key={i} className="mr-8 whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-gray-100 px-3 py-2 text-sm text-navy-800">
                  {item.text}
                </div>
              )
            if (item.kind === "tool")
              return (
                <div key={i} className="mr-8 flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-100/40 px-3 py-1.5 text-xs text-blue-600">
                  <Wrench className="size-3 shrink-0" />
                  <span className="font-bold">{item.name}:</span> {item.summary}
                </div>
              )
            return (
              <div key={i} className="mr-8 rounded-lg bg-red-50 px-3 py-1.5 text-xs text-error">
                {item.text}
              </div>
            )
          })}
          {busy && (
            <div className="mr-8 flex items-center gap-2 px-3 py-1 text-xs text-gray-400">
              <Loader2 className="size-3 animate-spin" /> pensando…
            </div>
          )}
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          send()
        }}
        className="flex gap-2 border-t border-gray-100 p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escríbele a la mascota…"
          className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="cursor-pointer rounded-lg bg-blue-500 px-3 text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send className="size-4" />
        </button>
      </form>
    </aside>
  )
}
