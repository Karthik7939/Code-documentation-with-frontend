import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requestRegeneration } from "@/lib/agentBackend";

export async function POST(req: NextRequest) {
  const { docId, comment } = await req.json();

  const updated = await db.updateDoc(docId, {
    status: "changes_requested",
    reviewComment: comment,
  });

  if (!updated) return NextResponse.json({ error: "Not found" }, { status: 404 });

  await requestRegeneration(docId, comment);

  return NextResponse.json(updated);
}