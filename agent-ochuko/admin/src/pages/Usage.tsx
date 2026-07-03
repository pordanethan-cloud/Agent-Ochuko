// src/pages/Usage.tsx
import { useEffect, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar,
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

const MODEL_NAME_MAP: Record<string, string> = {
  "gpt-5.4": "gpt-5.4 (Think)",
  "gpt-5.4-mini": "gpt-5.4-mini (Solve)",
  "gpt-5.4-pro": "gpt-5.4-mini (Solve)", // Map pro to mini as requested
  "gpt-5.4-nano": "gpt-5.4-nano (Discuss)",
  "unknown": "Other / Unknown"
};

// Colors for the specific models on the bar chart
const MODEL_COLORS: Record<string, string> = {
  "gpt-5.4": "#6366f1",      // Think: Indigo
  "gpt-5.4-mini": "#10b981", // Solve: Emerald
  "gpt-5.4-pro": "#10b981",  // Solve (legacy pro): Emerald
  "gpt-5.4-nano": "#f59e0b", // Discuss/Nano: Amber
  "unknown": "#64748b"       // Slate
};

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
    // Map the model name using our standard mapping (or fallback)
    const rawModel = m.model_used || "unknown";
    const mappedModel = MODEL_NAME_MAP[rawModel] ? rawModel : "unknown";
    byModel[mappedModel] = (byModel[mappedModel] ?? 0) + (m.input_tokens || 0) + (m.output_tokens || 0);
  });
  return Object.entries(byModel).map(([model, tokens]) => ({
    model,
    tokens,
    fill: MODEL_COLORS[model] || "#64748b"
  }));
}

export function Usage() {
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<number>(30);

  useEffect(() => {
    setLoading(true);
    adminGet<UsageResponse>(`/v1/admin/usage?days=${timeframe}`)
      .then(setData)
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [timeframe]);

  if (loading) return <Loading />;
  if (error)   return <ErrorMsg msg={error} />;
  if (!data)   return null;

  const dailyData = buildDailyData(data.messages);
  const modelData = buildModelData(data.messages);

  return (
    <div className="p-6 space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Usage Dashboard</h1>
          <p className="text-slate-400 text-sm">
            Token consumption metrics and distribution statistics.{" "}
            <span className="text-slate-600 text-xs italic">
              (Updates hourly once background aggregation is active.)
            </span>
          </p>
        </div>

        <div className="flex bg-slate-900 border border-slate-800 rounded-lg p-1 self-start sm:self-auto shadow-inner">
          {[
            { label: "Last Week", value: 7 },
            { label: "Last Month", value: 30 },
            { label: "Lifetime", value: 3650 },
          ].map(opt => (
            <button
              key={opt.value}
              onClick={() => setTimeframe(opt.value)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                timeframe === opt.value
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/10"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Daily token chart */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
        <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse"></span>
          Daily Token Consumption
        </h2>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={dailyData} margin={{ top: 10, left: 0, right: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35}/>
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis 
              dataKey="date" 
              tick={{ fill: "#94a3b8", fontSize: 10, fontWeight: 500 }} 
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
            />
            <YAxis 
              tick={{ fill: "#94a3b8", fontSize: 10, fontWeight: 500 }} 
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}
            />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 12, boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)' }}
              labelStyle={{ color: "#94a3b8", fontWeight: 600, fontSize: 11 }}
              itemStyle={{ color: "#818cf8", fontSize: 12 }}
              formatter={(value) => [Number(value).toLocaleString(), "Tokens"]}
            />
            <Area 
              type="monotone" 
              dataKey="tokens" 
              stroke="#6366f1" 
              strokeWidth={2} 
              fillOpacity={1} 
              fill="url(#colorTokens)" 
              name="Tokens" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Per-model bar chart */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
        <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
          Tokens by Model
        </h2>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={modelData} margin={{ top: 10, left: 0, right: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis 
              dataKey="model" 
              tick={{ fill: "#94a3b8", fontSize: 10, fontWeight: 500 }} 
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              tickFormatter={(m) => MODEL_NAME_MAP[m] || m}
            />
            <YAxis 
              tick={{ fill: "#94a3b8", fontSize: 10, fontWeight: 500 }} 
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}
            />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 12, boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)' }}
              itemStyle={{ color: "#34d399", fontSize: 12 }}
              labelStyle={{ color: "#94a3b8" }}
              formatter={(value) => [Number(value).toLocaleString(), "Tokens"]}
            />
            <Bar dataKey="tokens" radius={[6, 6, 0, 0]} name="Tokens" barSize={36} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top users table */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden shadow-lg backdrop-blur-sm">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400"></span>
            Top 5 Users by Token Consumption
          </h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs uppercase tracking-wider border-b border-slate-800 bg-slate-900/20">
              <th className="px-5 py-3 text-left">#</th>
              <th className="px-5 py-3 text-left">Email</th>
              <th className="px-5 py-3 text-right">Total Tokens</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {data.top_users.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-8 text-center text-slate-500 text-xs">
                  No data yet — data will appear after usage accrues.
                </td>
              </tr>
            ) : (
              data.top_users.map((u, i) => (
                <tr key={u.user_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-5 py-3.5 text-slate-500 font-semibold">{i + 1}</td>
                  <td className="px-5 py-3.5">
                    <div className="text-slate-200 font-medium">{u.email}</div>
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-slate-300 font-semibold">
                    {u.total_tokens.toLocaleString()}
                  </td>
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
    <div className="p-6 flex flex-col items-center justify-center h-64 text-slate-400 text-sm space-y-3">
      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
      <div>Loading usage data…</div>
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="p-6 flex items-center justify-center h-64">
      <div className="text-red-400 text-sm bg-red-950/20 border border-red-900/30 rounded-xl px-6 py-4">
        {msg}
      </div>
    </div>
  );
}
