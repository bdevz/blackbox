import { useState } from "react";
import { useParams, Link } from "react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Markdown from "react-markdown";
import { ArrowLeft, Download, RefreshCw, Send, Pencil, Save } from "lucide-react";
import { api } from "../lib/api";
import { downloadBlob } from "../lib/utils";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { StatusBadge, SeverityBadge, Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";

const TABS = ["solution", "compliance", "cost", "assembled"] as const;
type Tab = (typeof TABS)[number];

export function ProposalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("solution");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

  const proposal = useQuery({
    queryKey: ["proposal", id],
    queryFn: () => api.getProposal(id!),
    refetchInterval: (query) => query.state.data?.status === "generating" ? 5_000 : false,
  });

  const saveMutation = useMutation({
    mutationFn: (data: any) => api.updateProposal(id!, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["proposal", id] }); setEditing(false); },
  });

  const assembleMutation = useMutation({
    mutationFn: () => api.assembleProposal(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposal", id] }),
  });

  const submitMutation = useMutation({
    mutationFn: () => api.submitProposal(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposal", id] }),
  });

  const outcomeMutation = useMutation({
    mutationFn: (outcome: string) => api.updateOutcome(id!, outcome),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposal", id] }),
  });

  if (proposal.isLoading) return <div className="space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-32 w-full" />)}</div>;
  if (!proposal.data) return <p className="text-gray-500">Proposal not found</p>;

  const p = proposal.data;
  const review = p.review_result || {};
  const score = review.quality_score;

  const getContent = (): string => {
    if (tab === "solution") return p.solution_section || "";
    if (tab === "compliance") return p.compliance_section || "";
    if (tab === "cost") return p.cost_section?.narrative || JSON.stringify(p.cost_section, null, 2);
    return p.assembled_document || "*Not assembled yet*";
  };

  const handleEdit = () => {
    setEditText(tab === "solution" ? p.solution_section || "" : p.compliance_section || "");
    setEditing(true);
  };

  const handleSave = () => {
    const field = tab === "solution" ? "solution_section" : "compliance_section";
    saveMutation.mutate({ [field]: editText });
  };

  const handleExport = async (format: "pdf" | "docx") => {
    const blob = format === "pdf" ? await api.exportPdf(id!) : await api.exportDocx(id!);
    downloadBlob(blob, `proposal_${id!.slice(0, 8)}.${format}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/proposals" className="text-gray-400 hover:text-gray-600"><ArrowLeft className="w-5 h-5" /></Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900">Proposal</h1>
            <StatusBadge status={p.status} />
          </div>
          <p className="text-sm text-gray-500 mt-0.5">ID: {p.id}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Main content — left 2 cols */}
        <div className="col-span-2 space-y-4">
          {/* Tab bar */}
          <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setEditing(false); }}
                className={`flex-1 text-sm py-1.5 rounded-md capitalize transition-colors ${tab === t ? "bg-white shadow-sm font-medium text-gray-900" : "text-gray-500 hover:text-gray-700"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Content area */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <h3 className="text-sm font-medium text-gray-700 capitalize">{tab} Section</h3>
              {(tab === "solution" || tab === "compliance") && !editing && (
                <button onClick={handleEdit} className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1">
                  <Pencil className="w-3 h-3" /> Edit
                </button>
              )}
              {editing && (
                <button onClick={handleSave} disabled={saveMutation.isPending} className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
                  <Save className="w-3 h-3" /> {saveMutation.isPending ? "Saving..." : "Save"}
                </button>
              )}
            </CardHeader>
            <CardContent>
              {editing ? (
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full h-96 font-mono text-sm border border-gray-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
                />
              ) : (
                <div className="prose prose-sm prose-gray max-w-none">
                  <Markdown>{getContent() || "*No content yet*"}</Markdown>
                </div>
              )}

              {/* Cost table for cost tab */}
              {tab === "cost" && p.cost_section?.labor_costs?.roles && (
                <table className="w-full text-sm mt-4 border border-gray-200 rounded-lg overflow-hidden">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Role</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Rate</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Hours</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.cost_section.labor_costs.roles.map((r: any, i: number) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="px-4 py-2 font-medium">{r.title}</td>
                        <td className="px-4 py-2 text-right text-gray-600">${r.rate}</td>
                        <td className="px-4 py-2 text-right text-gray-600">{r.hours}</td>
                        <td className="px-4 py-2 text-right font-medium">${r.total?.toLocaleString()}</td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-gray-300 font-semibold">
                      <td className="px-4 py-2" colSpan={3}>Total</td>
                      <td className="px-4 py-2 text-right">${p.cost_section.total?.toLocaleString()}</td>
                    </tr>
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right sidebar — review + actions */}
        <div className="space-y-4">
          {/* Quality score */}
          <Card>
            <CardContent className="text-center py-6">
              <p className="text-xs font-medium text-gray-500 uppercase">Quality Score</p>
              <p className={`text-5xl font-bold mt-2 ${score >= 0.8 ? "text-emerald-500" : score >= 0.5 ? "text-amber-500" : score != null ? "text-red-500" : "text-gray-200"}`}>
                {score != null ? `${Math.round(score * 100)}` : "—"}
              </p>
              {review.recommendation && (
                <div className="mt-3">
                  <Badge variant={review.recommendation === "ready" ? "green" : review.recommendation === "needs_revision" ? "amber" : "red"}>
                    {review.recommendation?.replace(/_/g, " ")}
                  </Badge>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Contradictions */}
          {review.contradictions?.length > 0 && (
            <Card>
              <CardHeader><h3 className="text-sm font-medium text-gray-700">Issues ({review.contradictions.length})</h3></CardHeader>
              <CardContent className="space-y-3">
                {review.contradictions.map((c: any, i: number) => (
                  <div key={i} className="text-sm">
                    <div className="flex items-center gap-2 mb-1">
                      <SeverityBadge severity={c.severity} />
                      <span className="text-xs text-gray-400">{c.sections?.join(" / ")}</span>
                    </div>
                    <p className="text-gray-600">{c.issue}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Human scoring */}
          <Card>
            <CardHeader><h3 className="text-sm font-medium text-gray-700">Human Review</h3></CardHeader>
            <CardContent>
              <HumanScoring proposalId={id!} scores={p.human_review_scores || {}} />
            </CardContent>
          </Card>

          {/* Actions */}
          <Card>
            <CardContent className="space-y-2">
              <button onClick={() => handleExport("pdf")} className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
                <Download className="w-4 h-4 text-gray-400" /> Download PDF
              </button>
              <button onClick={() => handleExport("docx")} className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
                <Download className="w-4 h-4 text-gray-400" /> Download DOCX
              </button>
              <button onClick={() => assembleMutation.mutate()} disabled={assembleMutation.isPending} className="w-full flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
                <RefreshCw className={`w-4 h-4 text-gray-400 ${assembleMutation.isPending ? "animate-spin" : ""}`} /> Re-assemble
              </button>
              <button onClick={() => submitMutation.mutate()} disabled={p.status === "submitted"} className="w-full flex items-center gap-2 px-3 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors">
                <Send className="w-4 h-4" /> Submit Proposal
              </button>
              <div className="pt-2 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-1.5">Outcome</p>
                <select
                  value={p.outcome || "pending"}
                  onChange={(e) => outcomeMutation.mutate(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {["pending", "won", "lost", "interview", "no_response"].map((o) => (
                    <option key={o} value={o}>{o.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function HumanScoring({ proposalId, scores }: { proposalId: string; scores: Record<string, any> }) {
  const [values, setValues] = useState(scores);
  const queryClient = useQueryClient();

  const saveMutation = useMutation({
    mutationFn: (data: any) => api.updateProposal(proposalId, { human_review_scores: data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposal", proposalId] }),
  });

  const fields = ["technical", "compliance", "cost", "overall"];

  return (
    <div className="space-y-3">
      {fields.map((field) => (
        <div key={field} className="flex items-center justify-between">
          <label className="text-xs text-gray-500 capitalize">{field}</label>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                onClick={() => setValues({ ...values, [field]: n })}
                className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                  (values[field] || 0) >= n ? "bg-blue-500 text-white" : "bg-gray-100 text-gray-400 hover:bg-gray-200"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      ))}
      <button
        onClick={() => saveMutation.mutate(values)}
        disabled={saveMutation.isPending}
        className="w-full mt-2 px-3 py-1.5 text-xs bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors"
      >
        {saveMutation.isPending ? "Saving..." : "Save Scores"}
      </button>
    </div>
  );
}
