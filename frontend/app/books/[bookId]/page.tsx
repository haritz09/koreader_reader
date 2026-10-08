"use client";

import { useParams } from "next/navigation";
import { GraphView } from "@/components/graph-view";

export default function BookPage() {
  const params = useParams();
  const bookId = params.bookId as string;

  return (
    <main className="min-h-screen bg-surface-light px-6 py-8 dark:bg-surface-dark md:px-12 lg:px-16">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Grafo de conocimiento
          </h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Entidades, relaciones y eventos visibles en tu posición actual de
            lectura
          </p>
        </header>

        <GraphView bookId={bookId} />
      </div>
    </main>
  );
}
