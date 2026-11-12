import { createClient } from "@supabase/supabase-js"

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

if (!url || !anonKey) {
  // Falla visible en dev: sin estas vars no hay login.
  console.error("Faltan VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY (ver web/.env.example)")
}

export const supabase = createClient(url ?? "", anonKey ?? "")
