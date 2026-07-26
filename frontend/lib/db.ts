import { Repo, DocVersion, DocStatus } from "@/types";
import { getGeneratedDoc, listGeneratedDocs } from "@/lib/backendDocs";

let repos: Repo[] = [];
let docs: DocVersion[] = [];

export const db = {
  // repos
  listRepos: async (): Promise<Repo[]> => repos,

  getRepo: async (id: string): Promise<Repo | undefined> =>
    repos.find((r) => r.id === id),

  addRepo: async (repo: Repo): Promise<Repo> => {
    repos.push(repo);
    return repo;
  },

  // docs
  listDocs: async (): Promise<DocVersion[]> => {
    const generatedDocs = await listGeneratedDocs();
    docs = generatedDocs.map((document) => {
      const localDocument = docs.find((existing) => existing.id === document.id);
      return localDocument ? { ...document, ...localDocument } : document;
    });
    return docs;
  },

  getDoc: async (id: string): Promise<DocVersion | undefined> => {
    const generatedDoc = await getGeneratedDoc(id);
    if (!generatedDoc) return undefined;

    const localDocument = docs.find((document) => document.id === id);
    const document = localDocument
      ? { ...generatedDoc, ...localDocument, content: generatedDoc.content }
      : generatedDoc;
    const index = docs.findIndex((existing) => existing.id === id);
    if (index === -1) docs.push(document);
    else docs[index] = document;
    return document;
  },

  addDoc: async (doc: DocVersion): Promise<DocVersion> => {
    docs.push(doc);
    return doc;
  },

  updateDoc: async (
    id: string,
    updates: Partial<DocVersion>
  ): Promise<DocVersion | undefined> => {
    const idx = docs.findIndex((d) => d.id === id);
    if (idx === -1) return undefined;
    docs[idx] = { ...docs[idx], ...updates };
    return docs[idx];
  },

  setDocStatus: async (
    id: string,
    status: DocStatus
  ): Promise<DocVersion | undefined> => db.updateDoc(id, { status }),
};
