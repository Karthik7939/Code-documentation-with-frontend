import { db } from "@/lib/db";
import DocPreview from "@/components/DocPreview";
import DiffViewer from "@/components/DiffViewer";
import ApprovalActions from "@/components/ApprovalActions";
import { notFound } from "next/navigation";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  const { docId } = await params;
  const doc = await db.getDoc(docId);
  if (!doc) notFound();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{doc.title.split("/").at(-1)}</h1>
        <p className="mt-1 break-words text-sm text-muted">{doc.title}</p>
        <p className="mt-1 text-xs text-muted">
          Generated {new Date(doc.createdAt).toLocaleString()}
        </p>
      </div>

      <ApprovalActions docId={doc.id} />

      <div>
        <h2 className="text-sm font-medium text-muted mb-2">Preview</h2>
        <DocPreview content={doc.content} />
      </div>

      {doc.previousContent && (
        <div>
          <h2 className="text-sm font-medium text-muted mb-2">
            Changes vs last published version
          </h2>
          <DiffViewer oldText={doc.previousContent} newText={doc.content} />
        </div>
      )}
    </div>
  );
}
