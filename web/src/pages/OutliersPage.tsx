// Tablero de outliers — placeholder de Fase 0; se llena en Fase 2.

import { EmptyState } from "@/components/ui"

export function OutliersPage() {
  return (
    <div>
      <h1 className="mb-1 text-2xl">Outliers</h1>
      <p className="mb-8 text-sm text-gray-500">
        Contenido sobre-rindiendo en tu nicho, ordenado por multiplicador sobre la mediana del
        autor.
      </p>
      <EmptyState
        title="Todavía no hay datos"
        hint="Cuando tu perfil de nicho tenga una ingesta completa, el tablero se llena solo."
      />
    </div>
  )
}
