// Login con magic link (Supabase Auth). Sin contraseñas.

import { useState, type FormEvent } from "react"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui"

export function LoginPage() {
  const [email, setEmail] = useState("")
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    })
    setLoading(false)
    if (error) setError(error.message)
    else setSent(true)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-xl border border-gray-100 bg-white p-8 shadow-md">
        <img src="/brand/logo-full-light.png" alt="Orkiza" className="mx-auto mb-2 w-40" />
        <p className="label mb-8 text-center">VirtualOS</p>
        {sent ? (
          <p className="text-center text-sm text-gray-600">
            Te enviamos un enlace de acceso a <b>{email}</b>. Revisa tu correo y ábrelo en este
            navegador.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="label">Correo</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@correo.com"
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
              />
            </label>
            {error && <p className="text-xs font-bold text-error">{error}</p>}
            <Button type="submit" disabled={loading || !email}>
              {loading ? "Enviando..." : "Enviar enlace de acceso"}
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
