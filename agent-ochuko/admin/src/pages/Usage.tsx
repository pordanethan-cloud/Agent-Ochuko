// src/pages/Usage.tsx
import { useEffect, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { adminGet, adminPatch } from "../utils/api";
import { CreditCard, DollarSign, TrendingUp, AlertTriangle } from "lucide-react";

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
  azure_actual_cost?: number;
  azure_credit_limit?: number;
  azure_is_fallback?: boolean;
  azure_balance?: number;
}

const MODEL_NAME_MAP: Record<string, string> = {
  "gpt-5.4": "gpt-5.4 (Think)",
  "gpt-5.4-mini": "gpt-5.4-mini (Solve)",
  "gpt-5.4-pro": "gpt-5.4-mini (Solve)", // Map pro to mini
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
    const rawModel = m.model_used || "unknown";
    const mappedModel = MODEL_NAME_MAP[rawModel] ? rawModel : "unknown";
    byModel[mappedModel] = (byModel[mappedModel] ?? 0) + (m.input_tokens || 0) + (m.output_tokens || 0);
  });
  return Object.entries(byModel)
    .filter(([_, tokens]) => tokens > 0)
    .map(([model, tokens]) => ({
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

  // Credit limit state edit
  const [editingLimit, setEditingLimit] = useState(false);
  const [limitVal, setLimitVal] = useState("");
  const [savingLimit, setSavingLimit] = useState(false);

  const fetchUsage = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const res = await adminGet<UsageResponse>(`/v1/admin/usage?days=${timeframe}`);
      setData(res);
      if (res.azure_credit_limit !== undefined) {
        setLimitVal(res.azure_credit_limit.toString());
      }
    } catch (e: any) {
      setError(e.message || "An error occurred");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsage(true);
  }, [timeframe]);

  const handleSaveLimit = async () => {
    const numericLimit = parseFloat(limitVal);
    if (isNaN(numericLimit) || numericLimit < 0) {
      alert("Please enter a valid positive number for the credit limit.");
      return;
    }

    setSavingLimit(true);
    try {
      await adminPatch("/v1/admin/settings", {
        updates: { azure_monthly_credit_limit: limitVal },
      });
      setEditingLimit(false);
      // Silent refresh of data to update cards
      await fetchUsage(false);
    } catch (e: any) {
      alert(e.message || "Failed to update limit.");
    } finally {
      setSavingLimit(false);
    }
  };

  if (loading) return <Loading />;
  if (error)   return <ErrorMsg msg={error} />;
  if (!data)   return null;

  const dailyData = buildDailyData(data.messages);
  const modelData = buildModelData(data.messages);

  const actualCost = data.azure_actual_cost ?? 0;
  const creditLimit = data.azure_credit_limit ?? 150.00;
  const isFallback = data.azure_is_fallback ?? true;
  const balance = data.azure_balance ?? (creditLimit - actualCost);

  return (
    <div className="p-6 space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Usage & Billing</h1>
          <p className="text-slate-400 text-sm">
            Azure credit consumption, remaining balance, and token statistics.
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

      {/* Azure Billing Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Monthly Cost */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg relative overflow-hidden backdrop-blur-sm">
          <div className="flex justify-between items-start">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Monthly Subscription Cost
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold text-white">${actualCost.toFixed(2)}</span>
                {isFallback && (
                  <span className="text-[10px] font-semibold bg-amber-500/15 border border-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <AlertTriangle className="w-2.5 h-2.5" />
                    Est. Fallback
                  </span>
                )}
              </div>
            </div>
            <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/40 text-slate-400">
              <DollarSign className="w-5 h-5" />
            </div>
          </div>
          <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
            {isFallback 
              ? "Calculated in-database estimation of OpenAI token consumption for the current calendar month." 
              : "Pre-tax accumulated billing costs fetched from the Azure Cost Management API."}
          </p>
        </div>

        {/* Card 2: Credit Limit */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg relative overflow-hidden backdrop-blur-sm">
          <div className="flex justify-between items-start">
            <div className="space-y-1 flex-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Subscription Credit Limit
              </span>
              {editingLimit ? (
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={limitVal}
                    onChange={e => setLimitVal(e.target.value)}
                    className="w-24 bg-slate-850 border border-slate-700 rounded px-2 py-1 text-sm font-semibold text-white focus:outline-none focus:border-indigo-500"
                    disabled={savingLimit}
                  />
                  <button
                    onClick={handleSaveLimit}
                    disabled={savingLimit}
                    className="px-2 py-1 bg-indigo-650 hover:bg-indigo-600 text-white text-xs font-semibold rounded disabled:opacity-50"
                  >
                    {savingLimit ? "..." : "Save"}
                  </button>
                  <button
                    onClick={() => {
                      setEditingLimit(false);
                      setLimitVal(creditLimit.toString());
                    }}
                    disabled={savingLimit}
                    className="px-2 py-1 bg-slate-800 hover:bg-slate-750 text-slate-300 text-xs font-semibold rounded"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-3xl font-bold text-white">${creditLimit.toFixed(2)}</span>
                  <button
                    onClick={() => setEditingLimit(true)}
                    className="text-[10px] text-slate-500 hover:text-slate-350 underline font-semibold transition-colors"
                  >
                    Edit Limit
                  </button>
                </div>
              )}
            </div>
            <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/40 text-slate-400">
              <CreditCard className="w-5 h-5" />
            </div>
          </div>
          <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
            The configured budget ceiling. Updates modify the `azure_monthly_credit_limit` database setting.
          </p>
        </div>

        {/* Card 3: Remaining Balance */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg relative overflow-hidden backdrop-blur-sm">
          <div className="flex justify-between items-start">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Remaining Balance
              </span>
              <div className="flex items-baseline gap-1">
                <span className={`text-3xl font-bold ${balance <= 15 ? 'text-rose-450' : 'text-emerald-450'}`}>
                  ${balance.toFixed(2)}
                </span>
              </div>
            </div>
            <div className={`p-3 rounded-xl border ${balance <= 15 ? 'bg-rose-950/20 border-rose-900/30 text-rose-400' : 'bg-emerald-950/20 border-emerald-900/30 text-emerald-400'}`}>
              <TrendingUp className="w-5 h-5" />
            </div>
          </div>
          <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
            Remaining credit. When exhausted, non-admin API requests will fail with a credit limit warning.
          </p>
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
