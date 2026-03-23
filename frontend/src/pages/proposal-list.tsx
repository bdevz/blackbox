import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../lib/api";
import { formatDate } from "../lib/utils";
import { Card, CardContent } from "../components/ui/card";
import { StatusBadge, Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";

export function ProposalListPage() {
  const proposals = useQuery({
    queryKey: ["proposals"],
    queryFn: () => api.listProposals({ limit: 100 }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasGenerating = data?.some((p: any) => p.status === "generating");
      return hasGenerating ? 5_000 : 30_000;
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Proposals</h1>
        <p className="text-sm text-gray-500 mt-1">{proposals.data?.length ?? 0} total</p>
      </div>

      <Card>
        <CardContent className="p-0">
          {proposals.isLoading ? (
            <div className="p-6 space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">RFP</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Quality</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Outcome</th>
                  <th className="px-5 py-3 text-right text-xs font-medium text-gray-500 uppercase">Updated</th>
                </tr>
              </thead>
              <tbody>
                {(proposals.data ?? []).map((p: any) => {
                  const score = p.review_result?.quality_score;
                  return (
                    <tr key={p.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                      <td className="px-5 py-3">
                        <Link to={`/proposals/${p.id}`} className="font-medium text-gray-900 hover:text-blue-600 transition-colors">
                          Proposal
                        </Link>
                        <p className="text-xs text-gray-400 mt-0.5">ID: {p.id.slice(0, 8)}</p>
                      </td>
                      <td className="px-5 py-3"><StatusBadge status={p.status} /></td>
                      <td className="px-5 py-3">
                        {score != null ? (
                          <span className={`text-sm font-medium ${score >= 0.8 ? "text-emerald-600" : score >= 0.5 ? "text-amber-600" : "text-red-600"}`}>
                            {Math.round(score * 100)}%
                          </span>
                        ) : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-5 py-3">
                        <Badge variant={p.outcome === "won" ? "emerald" : p.outcome === "lost" ? "red" : "default"}>
                          {p.outcome || "pending"}
                        </Badge>
                      </td>
                      <td className="px-5 py-3 text-right text-gray-500">{formatDate(p.updated_at)}</td>
                    </tr>
                  );
                })}
                {(!proposals.data || proposals.data.length === 0) && (
                  <tr><td colSpan={5} className="px-5 py-12 text-center text-gray-400">
                    No proposals yet. <Link to="/rfps" className="text-blue-600 hover:underline">Upload an RFP</Link> to get started.
                  </td></tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
