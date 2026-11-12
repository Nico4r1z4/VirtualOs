// Shell de VirtualOS: sidebar con logo Orkiza + navegación de herramientas.
// La mascota vivirá en un panel lateral derecho (Fase 4); el centro son las
// herramientas densas (tablero, tendencias, ganchos, brief).

import { NavLink, Outlet } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { MascotPanel } from "@/components/MascotPanel"
import { CalendarRange, Flame, LogOut, Radar, Sparkles } from "lucide-react"
import { supabase } from "@/lib/supabase"
import { Toaster } from "@/components/ui"

const NAV = [
  { to: "/", label: "Outliers", icon: Flame },
  { to: "/tendencias", label: "Tendencias", icon: Radar },
  { to: "/ganchos", label: "Ganchos", icon: Sparkles },
  { to: "/brief", label: "Brief semanal", icon: CalendarRange },
]

export function Layout() {
  // Onboarding: si el workspace no tiene perfil de nicho, la mascota abre sola.
  const { data: profiles, isFetched } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.profiles,
  })
  const needsOnboarding = isFetched && (profiles?.items.length ?? 0) === 0

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-white px-5 py-8">
        <img src="/brand/logo-full-light.png" alt="Orkiza" className="mb-1 w-36" />
        <p className="label mb-10 mt-2">VirtualOS</p>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-bold transition-colors ${
                  isActive
                    ? "bg-blue-100 text-blue-600"
                    : "text-gray-500 hover:bg-gray-100 hover:text-navy-800"
                }`
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => supabase.auth.signOut()}
          className="mt-auto flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
        >
          <LogOut className="size-3.5" />
          Cerrar sesión
        </button>
      </aside>
      <main className="min-w-0 flex-1 px-10 py-8">
        <Outlet />
      </main>
      {isFetched && <MascotPanel key={String(needsOnboarding)} startOpen={needsOnboarding} />}
      <Toaster />
    </div>
  )
}
