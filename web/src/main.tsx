import { StrictMode, useEffect, useState, type ReactNode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import type { Session } from "@supabase/supabase-js"
import "./index.css"
import { supabase } from "@/lib/supabase"
import { Layout } from "@/components/Layout"
import { Spinner } from "@/components/ui"
import { LoginPage } from "@/pages/LoginPage"
import { OutliersPage } from "@/pages/OutliersPage"

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 3000 } },
})

function RequireAuth({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  if (!ready) return <Spinner />
  if (!session) return <LoginPage />
  return <>{children}</>
}

function Placeholder({ title }: { title: string }) {
  return (
    <div>
      <h1 className="mb-1 text-2xl">{title}</h1>
      <p className="text-sm text-gray-500">Disponible en una fase posterior del MVP.</p>
    </div>
  )
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <RequireAuth>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<OutliersPage />} />
              <Route path="/tendencias" element={<Placeholder title="Tendencias" />} />
              <Route path="/ganchos" element={<Placeholder title="Ganchos" />} />
              <Route path="/brief" element={<Placeholder title="Brief semanal" />} />
            </Route>
          </Routes>
        </RequireAuth>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
