import { diffLines } from "diff";

export default function DiffViewer({
  oldText,
  newText,
}: {
  oldText: string;
  newText: string;
}) {
  const changes = diffLines(oldText || "", newText || "");

  return (
    <div className="border border-border rounded-lg bg-surface overflow-hidden font-mono text-xs">
      {changes.map((part, i) => (
        <div
          key={i}
          className={
            part.added
              ? "bg-green-50 text-green-800 px-4 py-1 whitespace-pre-wrap"
              : part.removed
              ? "bg-red-50 text-red-800 px-4 py-1 whitespace-pre-wrap line-through"
              : "px-4 py-1 whitespace-pre-wrap text-muted"
          }
        >
          {part.value}
        </div>
      ))}
    </div>
  );
}