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
  estimated_cost?: number;  // computed client-side in dollars
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
  "gpt-5.4-pro": "gpt-5.4-mini (Solve)",
  "gpt-5.4-nano": "gpt-5.4-nano (Discuss)",
  "unknown": "Other / Unknown"
};

// Colors for the specific models
const MODEL_COLORS: Record<string, string> = {
  "gpt-5.4": "#6366f1",
  "gpt-5.4-mini": "#10b981",
  "gpt-5.4-pro": "#10b981",
  "gpt-5.4-nano": "#f59e0b",
  "unknown": "#64748b"
};

// ---------------------------------------------------------------------------
// Azure OpenAI pricing (USD per 1K tokens, approximate public rates)
// Input tokens are cheaper than output tokens.
// ---------------------------------------------------------------------------
const TOKEN_COST_PER_1K: Record<string, { input: number; output: number }> = {
  "gpt-5.4":      { input: 0.010, output: 0.030 },  // Think — flagship
  "gpt-5.4-mini": { input: 0.003, output: 0.012 },  // Solve — mini
  "gpt-5.4-pro":  { input: 0.003, output: 0.012 },  // legacy pro → same as mini
  "gpt-5.4-nano": { input: 0.001, output: 0.004 },  // Discuss/Nano — cheapest
  "unknown":      { input: 0.003, output: 0.012 },  // fallback to mini rates
};

/** Estimate dollar cost for a single message row. */
function estimateMsgCost(m: Message): number {
  const rates = TOKEN_COST_PER_1K[m.model_used] ?? TOKEN_COST_PER_1K["unknown"];
  const inputCost  = ((m.input_tokens  || 0) / 1000) * rates.input;
  const outputCost = ((m.output_tokens || 0) / 1000) * rates.output;
  return inputCost + outputCost;
}

function buildDailyData(messages: Message[]) {
  const byDay: Record<string, { tokens: number; cost: number }> = {};
  messages.forEach(m => {
    const day = m.created_at.slice(0, 10);
    if (!byDay[day]) byDay[day] = { tokens: 0, cost: 0 };
    byDay[day].tokens += (m.input_tokens || 0) + (m.output_tokens || 0);
    byDay[day].cost   += estimateMsgCost(m);
  });
  return Object.entries(byDay)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { tokens, cost }]) => ({ date, tokens, cost: parseFloat(cost.toFixed(4)) }));
}

function buildModelData(messages: Message[]) {
  const byModel: Record<string, { tokens: number; cost: number }> = {};
  messages.forEach(m => {
    const rawModel = m.model_used || "unknown";
    const key = MODEL_NAME_MAP[rawModel] ? rawModel : "unknown";
    if (!byModel[key]) byModel[key] = { tokens: 0, cost: 0 };
    byModel[key].tokens += (m.input_tokens || 0) + (m.output_tokens || 0);
    byModel[key].cost   += estimateMsgCost(m);
  });
  return Object.entries(byModel)
    .filter(([_, d]) => d.tokens > 0)
    .map(([model, d]) => ({
      model,
      tokens: d.tokens,
      cost: parseFloat(d.cost.toFixed(4)),
      fill: MODEL_COLORS[model] || "#64748b"
    }));
}

/** Aggregate estimated cost per user_id from raw messages. */
function buildUserCosts(messages: Message[]): Record<string, number> {
  const costs: Record<string, number> = {};
  messages.forEach(m => {
    if (!m.user_id) return;
    costs[m.user_id] = (costs[m.user_id] ?? 0) + estimateMsgCost(m);
  });
  return costs;
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
  const userCosts = buildUserCosts(data.messages);

  // Enrich top_users with estimated_cost computed from raw messages
  const enrichedTopUsers = data.top_users.map(u => ({
    ...u,
    estimated_cost: userCosts[u.user_id] ?? 0,
  }));

  // Total estimated cost from messages (used as fallback when azure_actual_cost is 0)
  const totalEstimatedCost = Object.values(userCosts).reduce((s, c) => s + c, 0);

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

      {/* Daily Spend chart — estimated $ cost over time */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            Daily Estimated Spend
          </h2>
          <span className="text-[10px] text-slate-500 font-medium bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-full">
            Est. total: ${totalEstimatedCost.toFixed(4)}
          </span>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={dailyData} margin={{ top: 10, left: 0, right: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.35}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
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
              tickFormatter={(v) => `$${Number(v).toFixed(3)}`}
            />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 12, boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)' }}
              labelStyle={{ color: "#94a3b8", fontWeight: 600, fontSize: 11 }}
              itemStyle={{ color: "#34d399", fontSize: 12 }}
              formatter={(value) => [`$${Number(value).toFixed(4)}`, "Est. Cost (USD)"]}
            />
            <Area
              type="monotone"
              dataKey="cost"
              stroke="#10b981"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorCost)"
              name="Est. Cost"
            />
          </AreaChart>
        </ResponsiveContainer>
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
          <span className="text-[10px] text-slate-500">
            Estimated cost computed from token × model pricing
          </span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs uppercase tracking-wider border-b border-slate-800 bg-slate-900/20">
              <th className="px-5 py-3 text-left">#</th>
              <th className="px-5 py-3 text-left">Email</th>
              <th className="px-5 py-3 text-right">Total Tokens</th>
              <th className="px-5 py-3 text-right">Est. Cost (USD)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {enrichedTopUsers.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-slate-500 text-xs">
                  No data yet — data will appear after usage accrues.
                </td>
              </tr>
            ) : (
              enrichedTopUsers.map((u, i) => (
                <tr key={u.user_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-5 py-3.5 text-slate-500 font-semibold">{i + 1}</td>
                  <td className="px-5 py-3.5">
                    <div className="text-slate-200 font-medium">{u.email}</div>
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-slate-300 font-semibold">
                    {u.total_tokens.toLocaleString()}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <span className={`font-mono font-bold text-sm ${
                      (u.estimated_cost ?? 0) > 1
                        ? 'text-rose-400'
                        : (u.estimated_cost ?? 0) > 0.10
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}>
                      ${(u.estimated_cost ?? 0).toFixed(4)}
                    </span>
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
