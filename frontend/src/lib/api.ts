const API_BASE = "/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

function params(obj: Record<string, string | number | undefined>): string {
  const entries = Object.entries(obj).filter(([, v]) => v !== undefined);
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export const api = {
  // RFPs
  listRfps: (p?: { skip?: number; limit?: number; status?: string }) =>
    fetchAPI<any[]>(`/rfps${params(p ?? {})}`),
  getRfp: (id: string) => fetchAPI<any>(`/rfps/${id}`),
  uploadRfp: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/rfps/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  },
  ingestUrl: (url: string) =>
    fetchAPI<any>(`/rfps/ingest-url?url=${encodeURIComponent(url)}`, { method: "POST" }),

  // Proposals
  listProposals: (p?: { skip?: number; limit?: number; status?: string }) =>
    fetchAPI<any[]>(`/proposals${params(p ?? {})}`),
  getProposal: (id: string) => fetchAPI<any>(`/proposals/${id}`),
  generateProposal: (rfpId: string) =>
    fetchAPI<any>(`/proposals/${rfpId}/generate`, { method: "POST" }),
  updateProposal: (id: string, data: any) =>
    fetchAPI<any>(`/proposals/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  submitProposal: (id: string) =>
    fetchAPI<any>(`/proposals/${id}/submit`, { method: "POST" }),
  updateOutcome: (id: string, outcome: string) =>
    fetchAPI<any>(`/proposals/${id}/outcome`, { method: "PATCH", body: JSON.stringify({ outcome }) }),
  assembleProposal: (id: string) =>
    fetchAPI<any>(`/proposals/${id}/assemble`, { method: "POST" }),
  exportPdf: (id: string) => fetch(`${API_BASE}/proposals/${id}/export/pdf`).then(r => r.blob()),
  exportDocx: (id: string) => fetch(`${API_BASE}/proposals/${id}/export/docx`).then(r => r.blob()),

  // Dashboard
  getPipeline: () => fetchAPI<any>("/dashboard/pipeline"),
  getAgentStats: () => fetchAPI<any[]>("/dashboard/agents"),
  getCosts: () => fetchAPI<any>("/dashboard/costs"),
  getOutcomes: () => fetchAPI<any>("/dashboard/outcomes"),
  getDeadlines: () => fetchAPI<any[]>("/dashboard/deadlines"),
};
