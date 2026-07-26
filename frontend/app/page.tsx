import { db } from "@/lib/db";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const docs = await db.listDocs();
  const repos = await db.listRepos();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-muted text-sm mt-1">
          {repos.length} repositories connected · {docs.length} documents tracked
        </p>
      </div>

      <div className="border border-border rounded-lg bg-surface overflow-hidden">
        <div className="px-5 py-3 border-b border-border text-sm font-medium">
          Recent documentation
        </div>
        {docs.length === 0 ? (
          <p className="px-5 py-6 text-sm text-muted">
            No documents yet. Connect a repo to get started.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {docs.map((doc) => (
              <li key={doc.id} className="px-5 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{doc.title}</p>
                  <p className="text-xs text-muted mt-0.5">
                    {new Date(doc.createdAt).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={doc.status} />
                  <Link
                    href={`/review/${doc.id}`}
                    className="text-sm text-accent hover:underline"
                  >
                    Review
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    pending_review: "bg-yellow-50 text-yellow-700",
    approved: "bg-green-50 text-green-700",
    changes_requested: "bg-red-50 text-red-700",
    published: "bg-blue-50 text-blue-700",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] || ""}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}
