import { Repo } from "@/types";

export default function RepoCard({ repo }: { repo: Repo }) {
  return (
    <div className="border border-border rounded-lg bg-surface p-4 flex items-center justify-between">
      <div>
        <p className="text-sm font-medium">{repo.fullName}</p>
        <p className="text-xs text-muted mt-0.5">
          Connected {new Date(repo.connectedAt).toLocaleDateString()}
        </p>
      </div>
      <span
        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          repo.webhookActive
            ? "bg-green-50 text-green-700"
            : "bg-gray-100 text-gray-600"
        }`}
      >
        {repo.webhookActive ? "Webhook active" : "Inactive"}
      </span>
    </div>
  );
}