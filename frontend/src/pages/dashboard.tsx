import { useQuery } from "@tanstack/react-query";
import { FileText, Clock, TrendingUp, DollarSign, AlertTriangle } from "lucide-react";
import { api } from "../lib/api";
import { daysUntil } from "../lib/utils";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";

export function DashboardPage() {
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: api.getPipeline, refetchInterval: 30_000 });
  const outcomes = useQuery({ queryKey: ["outcomes"], queryFn: api.getOutcomes, refetchInterval: 30_000 });
  const costs = useQuery({ queryKey: ["costs"], queryFn: api.getCosts, refetchInterval: 30_000 });
  const deadlines = useQuery({ queryKey: ["deadlines"], queryFn: api.getDeadlines, refetchInterval: 30_000 });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.getAgentStats, refetchInterval: 30_000 });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Pipeline health and performance metrics</p>
      </div>

      {/* Pipeline status cards */}
      <div className="grid grid-cols-5 gap-4">
        {["queued", "generating", "draft", "reviewing", "submitted"].map((status) => (
          <Card key={status}>
            <CardContent className="py-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{status}</p>
              <p className="text-3xl font-semibold text-gray-900 mt-1">
                {pipeline.isLoading ? <Skeleton className="h-9 w-12" /> : pipeline.data?.[status] ?? 0}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="flex items-start gap-4 py-5">
            <div className="p-2 bg-emerald-50 rounded-lg">
              <TrendingUp className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Win Rate</p>
              <p className="text-2xl font-semibold text-gray-900">
                {outcomes.isLoading ? "—" : `${outcomes.data?.win_rate_pct ?? 0}%`}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {outcomes.data?.counts?.won ?? 0} won / {outcomes.data?.total ?? 0} total
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-start gap-4 py-5">
            <div className="p-2 bg-blue-50 rounded-lg">
              <DollarSign className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">API Cost</p>
              <p className="text-2xl font-semibold text-gray-900">
                {costs.isLoading ? "—" : `$${costs.data?.estimated_cost_usd?.toFixed(2) ?? "0.00"}`}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {costs.data?.total_calls ?? 0} API calls
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-start gap-4 py-5">
            <div className="p-2 bg-amber-50 rounded-lg">
              <FileText className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Active Proposals</p>
              <p className="text-2xl font-semibold text-gray-900">
                {pipeline.isLoading
                  ? "—"
                  : (pipeline.data?.queued ?? 0) + (pipeline.data?.generating ?? 0) + (pipeline.data?.draft ?? 0)}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">In pipeline</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Deadline radar + Agent performance */}
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-400" />
              <h3 className="text-sm font-medium text-gray-700">Upcoming Deadlines</h3>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {deadlines.isLoading ? (
              <div className="p-5 space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-5 w-full" />)}
              </div>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {(deadlines.data ?? []).slice(0, 5).map((rfp: any) => {
                    const days = rfp.deadline ? Math.ceil((new Date(rfp.deadline).getTime() - Date.now()) / 86_400_000) : null;
                    const urgency = days != null && days < 3 ? "text-red-600 font-medium" : days != null && days < 7 ? "text-amber-600" : "text-gray-500";
                    return (
                      <tr key={rfp.id} className="border-b border-gray-50 last:border-0">
                        <td className="px-5 py-3">
                          <p className="font-medium text-gray-900 truncate max-w-[200px]">{rfp.title}</p>
                          <p className="text-xs text-gray-400">{rfp.agency}</p>
                        </td>
                        <td className={`px-5 py-3 text-right text-xs ${urgency}`}>
                          {daysUntil(rfp.deadline)}
                        </td>
                      </tr>
                    );
                  })}
                  {(!deadlines.data || deadlines.data.length === 0) && (
                    <tr><td className="px-5 py-8 text-center text-gray-400" colSpan={2}>No upcoming deadlines</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-gray-400" />
              <h3 className="text-sm font-medium text-gray-700">Agent Performance</h3>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {agents.isLoading ? (
              <div className="p-5 space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-5 w-full" />)}
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="px-5 py-2 text-left text-xs font-medium text-gray-500">Agent</th>
                    <th className="px-5 py-2 text-right text-xs font-medium text-gray-500">Avg (ms)</th>
                    <th className="px-5 py-2 text-right text-xs font-medium text-gray-500">Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {(agents.data ?? []).map((a: any) => (
                    <tr key={a.agent} className="border-b border-gray-50 last:border-0">
                      <td className="px-5 py-2.5 font-medium text-gray-700 capitalize">{a.agent}</td>
                      <td className="px-5 py-2.5 text-right text-gray-500">{Math.round(a.avg_duration_ms)}</td>
                      <td className="px-5 py-2.5 text-right text-gray-500">{a.total_runs}</td>
                    </tr>
                  ))}
                  {(!agents.data || agents.data.length === 0) && (
                    <tr><td className="px-5 py-8 text-center text-gray-400" colSpan={3}>No agent data yet</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
