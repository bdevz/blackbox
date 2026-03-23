import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { Upload, Link as LinkIcon, Plus } from "lucide-react";
import { api } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/utils";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";

export function RfpListPage() {
  const [showUpload, setShowUpload] = useState(false);
  const rfps = useQuery({ queryKey: ["rfps"], queryFn: () => api.listRfps({ limit: 100 }) });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">RFPs</h1>
          <p className="text-sm text-gray-500 mt-1">{rfps.data?.length ?? 0} total</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors"
        >
          <Plus className="w-4 h-4" /> Upload RFP
        </button>
      </div>

      {showUpload && <UploadDialog onClose={() => setShowUpload(false)} />}

      <Card>
        <CardContent className="p-0">
          {rfps.isLoading ? (
            <div className="p-6 space-y-4">
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agency</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Deadline</th>
                  <th className="px-5 py-3 text-right text-xs font-medium text-gray-500 uppercase">Value</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                </tr>
              </thead>
              <tbody>
                {(rfps.data ?? []).map((rfp: any) => (
                  <tr key={rfp.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3">
                      <Link to={`/rfps/${rfp.id}`} className="font-medium text-gray-900 hover:text-blue-600 transition-colors">
                        {rfp.title}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-gray-600">{rfp.agency_name || "—"}</td>
                    <td className="px-5 py-3 text-gray-600">{formatDate(rfp.deadline)}</td>
                    <td className="px-5 py-3 text-right text-gray-600">{formatCurrency(rfp.estimated_value)}</td>
                    <td className="px-5 py-3"><Badge>{rfp.source}</Badge></td>
                  </tr>
                ))}
                {(!rfps.data || rfps.data.length === 0) && (
                  <tr><td colSpan={5} className="px-5 py-12 text-center text-gray-400">No RFPs yet. Upload one to get started.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function UploadDialog({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"file" | "url">("file");
  const [url, setUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: api.uploadRfp,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["rfps"] }); onClose(); },
  });

  const urlMutation = useMutation({
    mutationFn: api.ingestUrl,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["rfps"] }); onClose(); },
  });

  const handleFile = useCallback((file: File) => { uploadMutation.mutate(file); }, [uploadMutation]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <Card className="w-full max-w-md" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-base font-medium text-gray-900">Add RFP</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>
          <div className="flex gap-1 mt-3 bg-gray-100 p-1 rounded-lg">
            <button
              onClick={() => setTab("file")}
              className={`flex-1 text-sm py-1.5 rounded-md transition-colors ${tab === "file" ? "bg-white shadow-sm font-medium" : "text-gray-500"}`}
            >
              <Upload className="w-3.5 h-3.5 inline mr-1.5" />File Upload
            </button>
            <button
              onClick={() => setTab("url")}
              className={`flex-1 text-sm py-1.5 rounded-md transition-colors ${tab === "url" ? "bg-white shadow-sm font-medium" : "text-gray-500"}`}
            >
              <LinkIcon className="w-3.5 h-3.5 inline mr-1.5" />From URL
            </button>
          </div>
        </CardHeader>
        <CardContent>
          {tab === "file" ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${dragging ? "border-blue-400 bg-blue-50" : "border-gray-200"}`}
            >
              <Upload className="w-8 h-8 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-600">
                {uploadMutation.isPending ? "Uploading..." : "Drop PDF or DOCX here"}
              </p>
              <p className="text-xs text-gray-400 mt-1">or</p>
              <label className="mt-2 inline-block px-4 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-md cursor-pointer hover:bg-gray-200 transition-colors">
                Browse files
                <input type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
              </label>
            </div>
          ) : (
            <div className="space-y-3">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://..."
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => url && urlMutation.mutate(url)}
                disabled={!url || urlMutation.isPending}
                className="w-full px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 disabled:opacity-50 transition-colors"
              >
                {urlMutation.isPending ? "Ingesting..." : "Ingest from URL"}
              </button>
            </div>
          )}
          {(uploadMutation.isError || urlMutation.isError) && (
            <p className="mt-3 text-sm text-red-600">Upload failed. Try again.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
