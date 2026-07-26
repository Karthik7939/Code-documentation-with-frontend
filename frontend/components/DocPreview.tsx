import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function DocPreview({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-a:text-accent rounded-lg border border-border bg-surface p-5 sm:p-6">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
