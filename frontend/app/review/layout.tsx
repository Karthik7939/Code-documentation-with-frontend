import Link from "next/link";

import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function ReviewLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const documents = await db.listDocs();

  return (
    <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="border-b border-border px-3 py-2.5">
            <h2 className="text-sm font-semibold">Generated documentation</h2>
            <p className="mt-0.5 text-xs text-muted">
              {documents.length} document{documents.length === 1 ? "" : "s"}
            </p>
          </div>

          {documents.length === 0 ? (
            <p className="px-4 py-5 text-sm text-muted">
              No generated documentation is available yet.
            </p>
          ) : (
            <nav className="max-h-[calc(100vh-8rem)] overflow-y-auto p-1.5">
              {documents.map((document) => (
                <Link
                  key={document.id}
                  href={`/review/${document.id}`}
                  className="block rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-accent-soft"
                  title={document.title}
                >
                  <span className="block truncate font-medium">
                    {document.title.split("/").at(-1)}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-muted">
                    {document.title.split("/").slice(-3, -1).join("/")}
                  </span>
                </Link>
              ))}
            </nav>
          )}
        </div>
      </aside>

      <section className="min-w-0">{children}</section>
    </div>
  );
}
