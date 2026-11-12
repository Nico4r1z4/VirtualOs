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
// Tipos de dominio
// ---------------------------------------------------------------------------

export type Me = {
  user_id: string
  email: string | null
  workspace_id: string
}

export type OutlierPost = {
  id: string
  platform: "tiktok" | "instagram" | "facebook"
  external_id: string
  author_handle: string | null
  url: string | null
  published_at: string | null
  views: number | null
  likes: number | null
  comments: number | null
  shares: number | null
  caption: string | null
  hashtags: string[]
  sound_name: string | null
  duration_s: number | null
  thumbnail_url: string | null
  outlier_score: number | null
  velocity: number | null
  rank_score: number | null
}

export type Snapshot = {
  captured_at: string
  views: number | null
  likes: number | null
  comments: number | null
  shares: number | null
}

export type PostDetail = OutlierPost & {
  transcript: string | null
  snapshots: Snapshot[]
  hook: {
    hook_text: string
    hook_type: string | null
    structure: unknown
    cta: string | null
    language: string | null
  } | null
}

export type Trend = {
  id: string
  platform: string
  country: string
  trend_type: "hashtag" | "sound"
  name: string
  rank: number | null
  metrics: Record<string, unknown>
  captured_at: string
}

export type NicheProfile = {
  id: string
  status: "active" | "archived"
  kind: string
  name: string
  platforms: string[]
  countries: string[]
  languages: string[]
  keywords: string[]
  hashtags: string[]
  seed_accounts: Record<string, string[]>
  goals: string | null
  tone: string | null
  created_at: string
}

export type JobStatus = {
  id: string
  kind: string
  status: "pending" | "running" | "done" | "failed"
  attempts: number
  error: string | null
}

export type OutlierFilters = {
  platform?: string
  min_multiplier?: number
  date_from?: string
  date_to?: string
  sort?: "rank" | "outlier" | "views" | "velocity" | "recent"
  page?: number
  page_size?: number
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
  if (!entries.length) return ""
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")
}

export const api = {
  me: () => get<Me>("/me"),
  outliers: (f: OutlierFilters) =>
    get<{ items: OutlierPost[]; total: number; page: number; page_size: number }>(
      `/outliers${qs(f)}`,
    ),
  post: (id: string) => get<PostDetail>(`/posts/${id}`),
  trends: (platform = "tiktok", country?: string) =>
    get<{ items: Trend[] }>(`/trends${qs({ platform, country })}`),
  profiles: () => get<{ items: NicheProfile[] }>("/niche-profiles"),
  createProfile: (body: Partial<NicheProfile>) => post<NicheProfile>("/niche-profiles", body),
  startIngestion: (nicheProfileId: string) =>
    post<{ job_id: string; status: string }>("/ingestions", {
      niche_profile_id: nicheProfileId,
    }),
  job: (id: string) => get<JobStatus>(`/jobs/${id}`),
}

export { get, post }
