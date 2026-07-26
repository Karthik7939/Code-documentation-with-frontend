"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function ApprovalActions({ docId }: { docId: string }) {
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleApprove() {
    setLoading(true);
    await fetch("/api/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ docId }),
    });
    setLoading(false);
    router.push("/");
  }

  async function handleReject() {
    setLoading(true);
    await fetch("/api/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ docId, comment }),
    });
    setLoading(false);
    router.push("/");
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {!showComment ? (
        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            disabled={loading}
            className="bg-accent text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-[#8f4d20] transition-colors disabled:opacity-50"
          >
            Approve & Publish
          </button>
          <button
            onClick={() => setShowComment(true)}
            disabled={loading}
            className="border border-border text-sm font-medium px-4 py-2 rounded-md hover:bg-accent-soft transition-colors"
          >
            Request changes
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What should be changed?"
            rows={3}
            className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-soft"
          />
          <div className="flex gap-3">
            <button
              onClick={handleReject}
              disabled={loading || !comment}
              className="bg-danger text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-[#96382f] transition-colors disabled:opacity-50"
            >
              Send back for changes
            </button>
            <button
              onClick={() => setShowComment(false)}
              className="text-sm text-muted hover:text-text"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
