import Link from "next/link";

export default function Navbar() {
  return (
    <header className="border-b border-border bg-surface sticky top-0 z-10">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-5 sm:px-6">
        <Link href="/" className="font-semibold text-[15px] tracking-tight">
          DocAgent
        </Link>
        <nav className="flex gap-6 text-sm text-muted">
          <Link href="/" className="hover:text-text transition-colors">
            Dashboard
          </Link>
          <Link href="/repos" className="hover:text-text transition-colors">
            Repositories
          </Link>
          <Link href="/review" className="hover:text-text transition-colors">
            Documentation
          </Link>
          <Link href="/debug" className="hover:text-text transition-colors">
            Debugging
          </Link>
        </nav>
      </div>
    </header>
  );
}
