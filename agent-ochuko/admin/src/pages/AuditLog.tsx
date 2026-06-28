// src/pages/AuditLog.tsx
import { useEffect, useState, useCallback } from "react";
import { ChevronDown, ChevronRight, Download, ChevronLeft, ChevronRight as ChevRight } from "lucide-react";
import { adminGet } from "../utils/api";

interface Profile {
  email: string;
  full_name: string | null;
}

interface AuditEntry {
  id: string;
  created_at: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  policy_decision: "ALLOW" | "DENY";
  ip_address: string | null;
  user_agent: string | null;
  policy_reason: string | null;
  metadata: Record<string, unknown> | null;
  profiles: Profile | null;
}

interface AuditResponse {
  entries: AuditEntry[];
  page: number;
  page_size: number;
}

export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [action, setAction] = useState("");
  const [decision, setDecision] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const buildQuery = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (action)   params.set("action", action);
    if (decision) params.set("policy_decision", decision);
    if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
    if (dateTo)   params.set("date_to",   new Date(dateTo).toISOString());
    return `/v1/admin/audit?${params.toString()}`;
  }, [page, action, decision, dateFrom, dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminGet<AuditResponse>(buildQuery());
      setEntries(data.entries);
      setHasMore(data.entries.length === 50);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [buildQuery]);

  useEffect(() => { load(); }, [load]);

  const exportCSV = () => {
    const header = "timestamp,user,action,resource_type,policy_decision,ip_address";
    const rows = entries.map(e =>
      [
        e.created_at,
        e.profiles?.email ?? e.user_id,
        e.action,
        e.resource_type,
        e.policy_decision,
        e.ip_address ?? "",
      ]
        .map(v => `"${String(v).replace(/"/g, '""')}"`)
        .join(",")
    );
    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const fmt = (d: string) => new Date(d).toLocaleString();

  return (
    <div className="p-6">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Audit Log</h1>
          <p className="text-slate-400 text-sm">Complete record of admin actions and policy decisions.</p>
        </div>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm transition-colors"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          placeholder="Filter by action…"
          value={action}
          onChange={e => { setAction(e.target.value); setPage(1); }}
          className={filterInput}
        />
        <select
          aria-label="Filter by policy decision"
          value={decision}
          onChange={e => { setDecision(e.target.value); setPage(1); }}
          className={filterInput}
        >
          <option value="">All decisions</option>
          <option value="ALLOW">ALLOW</option>
          <option value="DENY">DENY</option>
        </select>
        <input
          type="date"
          aria-label="Filter from date"
          value={dateFrom}
          onChange={e => { setDateFrom(e.target.value); setPage(1); }}
          className={filterInput}
        />
        <input
          type="date"
          aria-label="Filter to date"
          value={dateTo}
          onChange={e => { setDateTo(e.target.value); setPage(1); }}
          className={filterInput}
        />
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 w-6"></th>
                <th className="px-4 py-3 text-left">Timestamp</th>
                <th className="px-4 py-3 text-left">User</th>
                <th className="px-4 py-3 text-left">Action</th>
                <th className="px-4 py-3 text-left">Resource</th>
                <th className="px-4 py-3 text-left">Decision</th>
                <th className="px-4 py-3 text-left">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">Loading…</td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-red-400">{error}</td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">No audit entries found.</td>
                </tr>
              ) : (
                entries.map(e => (
                  <>
                    <tr
                      key={e.id}
                      className="hover:bg-slate-800/50 transition-colors cursor-pointer"
                      onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    >
                      <td className="px-4 py-3 text-slate-600">
                        {expanded === e.id
                          ? <ChevronDown size={13} />
                          : <ChevronRight size={13} />}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{fmt(e.created_at)}</td>
                      <td className="px-4 py-3 text-slate-200">
                        {e.profiles?.email ?? <span className="text-slate-600 text-xs font-mono">{e.user_id.slice(0, 8)}…</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300">
                          {e.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400">{e.resource_type}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                          e.policy_decision === "ALLOW"
                            ? "bg-green-500/15 text-green-400"
                            : "bg-red-500/15 text-red-400"
                        }`}>
                          {e.policy_decision}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{e.ip_address ?? "—"}</td>
                    </tr>
                    {expanded === e.id && (
                      <tr key={`${e.id}-exp`} className="bg-slate-800/30">
                        <td colSpan={7} className="px-6 py-3">
                          <div className="text-xs text-slate-400 space-y-1">
                            {e.policy_reason && <div><span className="text-slate-500">Reason: </span>{e.policy_reason}</div>}
                            {e.user_agent && <div><span className="text-slate-500">User Agent: </span>{e.user_agent}</div>}
                            {e.resource_id && <div><span className="text-slate-500">Resource ID: </span><span className="font-mono">{e.resource_id}</span></div>}
                            {e.metadata && Object.keys(e.metadata).length > 0 && (
                              <div>
                                <div className="text-slate-500 mb-1">Metadata:</div>
                                <pre className="bg-slate-900 rounded p-2 text-slate-300 overflow-x-auto text-[11px]">
                                  {JSON.stringify(e.metadata, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800">
          <span className="text-xs text-slate-500">Page {page}</span>
          <div className="flex gap-2">
            <button
              aria-label="Previous page"
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
              className="p-1.5 rounded-lg hover:bg-slate-700 disabled:opacity-30 text-slate-400 transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              aria-label="Next page"
              disabled={!hasMore}
              onClick={() => setPage(p => p + 1)}
              className="p-1.5 rounded-lg hover:bg-slate-700 disabled:opacity-30 text-slate-400 transition-colors"
            >
              <ChevRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const filterInput = "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500";
