import { useParams, Link } from "react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Zap } from "lucide-react";
import { api } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/utils";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";

export function RfpDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const rfp = useQuery({ queryKey: ["rfp", id], queryFn: () => api.getRfp(id!) });

  const generateMutation = useMutation({
    mutationFn: () => api.generateProposal(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposals"] }),
  });

  if (rfp.isLoading) return <div className="space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}</div>;
  if (!rfp.data) return <p className="text-gray-500">RFP not found</p>;

  const r = rfp.data;
  const brief = r.extracted_brief || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/rfps" className="text-gray-400 hover:text-gray-600"><ArrowLeft className="w-5 h-5" /></Link>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold text-gray-900">{r.title}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{r.agency_name || "Unknown Agency"} &middot; {r.agency_state || ""}</p>
        </div>
        <button
          onClick={() => generateMutation.mutate()}
          disabled={generateMutation.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          <Zap className="w-4 h-4" />
          {generateMutation.isPending ? "Generating..." : "Generate Proposal"}
        </button>
      </div>

      {generateMutation.isSuccess && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-3 text-sm">
          Proposal queued for generation. <Link to="/proposals" className="underline font-medium">View proposals</Link>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Card><CardContent><p className="text-xs text-gray-500">Deadline</p><p className="font-medium mt-1">{formatDate(r.deadline)}</p></CardContent></Card>
        <Card><CardContent><p className="text-xs text-gray-500">Estimated Value</p><p className="font-medium mt-1">{formatCurrency(r.estimated_value)}</p></CardContent></Card>
        <Card><CardContent><p className="text-xs text-gray-500">Category</p><p className="font-medium mt-1">{r.category || "—"}</p></CardContent></Card>
      </div>

      {brief.requirements && brief.requirements.length > 0 && (
        <Card>
          <CardHeader><h3 className="text-sm font-medium text-gray-700">Requirements</h3></CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {brief.requirements.map((req: string, i: number) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                  <span className="mt-1 w-1.5 h-1.5 rounded-full bg-gray-300 shrink-0" />
                  {req}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {brief.scope && (
        <Card>
          <CardHeader><h3 className="text-sm font-medium text-gray-700">Scope of Work</h3></CardHeader>
          <CardContent><p className="text-sm text-gray-600 leading-relaxed">{brief.scope}</p></CardContent>
        </Card>
      )}

      {brief.evaluation_criteria && Object.keys(brief.evaluation_criteria).length > 0 && (
        <Card>
          <CardHeader><h3 className="text-sm font-medium text-gray-700">Evaluation Criteria</h3></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(brief.evaluation_criteria).map(([key, weight]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 capitalize">{key.replace(/_/g, " ")}</span>
                  <Badge>{String(weight)}%</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
