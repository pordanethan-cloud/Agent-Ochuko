// src/pages/Usage.tsx
import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { adminGet } from "../utils/api";

interface Message {
  user_id: string;
  input_tokens: number;
  output_tokens: number;
  model_used: string;
  created_at: string;
}

interface TopUser {
  user_id: string;
  email: string;
  total_tokens: number;
}

interface UsageResponse {
  messages: Message[];
  days: number;
  top_users: TopUser[];
}

function buildDailyData(messages: Message[]) {
  const byDay: Record<string, number> = {};
  messages.forEach(m => {
    const day = m.created_at.slice(0, 10);
    byDay[day] = (byDay[day] ?? 0) + (m.input_tokens || 0) + (m.output_tokens || 0);
  });
  return Object.entries(byDay)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, tokens]) => ({ date, tokens }));
}

function buildModelData(messages: Message[]) {
  const byModel: Record<string, number> = {};
  messages.forEach(m => {
    const model = m.model_used || "unknown";
    byModel[model] = (byModel[model] ?? 0) + (m.input_tokens || 0) + (m.output_tokens || 0);
  });
  return Object.entries(byModel).map(([model, tokens]) => ({ model, tokens }));
}

export function Usage() {
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminGet<UsageResponse>("/v1/admin/usage?days=30")
      .then(setData)
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading />;
  if (error)   return <ErrorMsg msg={error} />;
  if (!data)   return null;

  const dailyData = buildDailyData(data.messages);
  const modelData = buildModelData(data.messages);

  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Usage</h1>
        <p className="text-slate-400 text-sm">
          Token consumption over the last 30 days.{" "}
          <span className="text-slate-600 text-xs italic">
            (Updates hourly once background aggregation is active — Phase 6.)
          </span>
        </p>
      </div>

      {/* Daily token chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Daily Token Consumption</h2>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={dailyData} margin={{ left: 0, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
              labelStyle={{ color: "#94a3b8" }}
              itemStyle={{ color: "#818cf8" }}
            />
            <Line type="monotone" dataKey="tokens" stroke="#818cf8" strokeWidth={2} dot={false} name="Tokens" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Per-model bar chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Tokens by Model</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={modelData} margin={{ left: 0, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="model" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
              itemStyle={{ color: "#34d399" }}
            />
            <Bar dataKey="tokens" fill="#34d399" radius={[4, 4, 0, 0]} name="Tokens" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top users table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300">Top 5 Users by Token Consumption</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
              <th className="px-5 py-3 text-left">#</th>
              <th className="px-5 py-3 text-left">Email</th>
              <th className="px-5 py-3 text-right">Total Tokens</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {data.top_users.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-6 text-center text-slate-500 text-xs">
                  No data yet — the top-users RPC isn't seeded. Data will appear after usage accrues.
                </td>
              </tr>
            ) : (
              data.top_users.map((u, i) => (
                <tr key={u.user_id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-5 py-3 text-slate-500">{i + 1}</td>
                  <td className="px-5 py-3 text-slate-200">{u.email}</td>
                  <td className="px-5 py-3 text-right text-slate-300">{u.total_tokens.toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="p-6 flex items-center justify-center h-64 text-slate-500 text-sm">
      Loading usage data…
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="p-6 flex items-center justify-center h-64">
      <div className="text-red-400 text-sm bg-red-900/20 border border-red-700/30 rounded-xl px-6 py-4">
        {msg}
      </div>
    </div>
  );
}
