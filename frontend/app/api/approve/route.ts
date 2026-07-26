import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { publishToGitbook } from "@/lib/gitbook";

export async function POST(req: NextRequest) {
  const { docId } = await req.json();
  const doc = await db.getDoc(docId);

  if (!doc) return NextResponse.json({ error: "Doc not found" }, { status: 404 });

  const repo = await db.getRepo(doc.repoId);
  const spaceId = repo?.gitbookSpaceId || process.env.GITBOOK_SPACE_ID!;

  await publishToGitbook({
    spaceId,
    path: `${doc.title.toLowerCase().replace(/\s+/g, "-")}.md`,
    markdown: doc.content,
  });

  const updated = await db.setDocStatus(docId, "published");
  return NextResponse.json(updated);
}