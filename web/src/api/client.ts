// Cliente HTTP del API de VirtualOS. Adjunta el access token de Supabase en
// cada request; la API valida el JWT y aplica RLS por workspace.

import { supabase } from "@/lib/supabase"

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new ApiError(401, "Sin sesión")
  return { Authorization: `Bearer ${token}` }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: await authHeaders() })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Tipos de dominio (crecen por fase)
// ---------------------------------------------------------------------------

export type Me = {
  user_id: string
  email: string | null
  workspace_id: string
}

export const api = {
  me: () => get<Me>("/me"),
  health: async (): Promise<{ status: string }> => {
    const res = await fetch(`${BASE}/health`)
    if (!res.ok) throw new ApiError(res.status, await res.text())
    return res.json()
  },
}

export { get, post }
