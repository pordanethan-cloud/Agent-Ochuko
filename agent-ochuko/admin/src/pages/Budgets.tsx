// src/pages/Budgets.tsx
import { useEffect, useState, useCallback } from "react";
import { adminGet, adminPatch } from "../utils/api";
import { Toast } from "../components/Toast";

interface AdminSetting {
  key: string;
  value: string;
  description: string | null;
}

interface SettingsResponse {
  settings: AdminSetting[];
}

interface UserRow {
  id: string;
  email: string;
  full_name: string | null;
  token_budgets: { tokens_used: number; budget_limit: number } | null;
}

interface UsersResponse {
  users: UserRow[];
}

export function Budgets() {
  const [settings, setSettings] = useState<AdminSetting[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [globalBudget, setGlobalBudget] = useState("");
  const [budgetEdits, setBudgetEdits] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, u] = await Promise.all([
        adminGet<SettingsResponse>("/v1/admin/settings"),
        adminGet<UsersResponse>("/v1/admin/users?page=1&page_size=200"),
      ]);
      setSettings(s.settings);
      setUsers(u.users);
      const gb = s.settings.find(x => x.key === "global_daily_token_budget");
      if (gb) setGlobalBudget(gb.value);
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveGlobalBudget = async () => {
    try {
      await adminPatch("/v1/admin/settings", {
        updates: { global_daily_token_budget: globalBudget },
      });
      setToast({ msg: "Global token budget updated.", type: "success" });
      load();
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    }
  };

  const saveUserBudget = async (userId: string) => {
    const val = budgetEdits[userId];
    if (!val) return;
    try {
      await adminPatch(`/v1/admin/users/${userId}/budget`, { budget_limit: parseInt(val, 10) });
      setToast({ msg: "User budget updated.", type: "success" });
      load();
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    }
  };

  if (loading) return (
    <div className="p-6 flex items-center justify-center h-64 text-slate-500 text-sm">Loading…</div>
  );

  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Budgets</h1>
        <p className="text-slate-400 text-sm">Manage global and per-user daily token limits.</p>
      </div>

      {/* Global budget */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Global Default Daily Token Budget</h2>
        <div className="flex items-center gap-3 max-w-sm">
          <input
            type="number"
            min={0}
            aria-label="Global daily token budget"
            value={globalBudget}
            onChange={e => setGlobalBudget(e.target.value)}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={saveGlobalBudget}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-colors"
          >
            Save
          </button>
        </div>
        <p className="text-slate-600 text-xs mt-2">
          Applies to all users without a custom override. Currently stored in admin_settings.
        </p>
      </div>

      {/* Per-user budgets */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300">Per-User Budget Overrides</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs uppercase tracking-wider border-b border-slate-800">
              <th className="px-5 py-3 text-left">User</th>
              <th className="px-5 py-3 text-left">Usage</th>
              <th className="px-5 py-3 text-left">Custom Limit</th>
              <th className="px-5 py-3 text-left"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {users.map(u => {
              const used = u.token_budgets?.tokens_used ?? 0;
              const limit = u.token_budgets?.budget_limit ?? 0;
              const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
              const progressProps = {
                "aria-valuenow": pct,
                "aria-valuemin": 0,
                "aria-valuemax": 100,
                style: { width: `${pct}%` }
              };
              return (
                <tr key={u.id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-5 py-3">
                    <div className="text-slate-200">{u.full_name || "—"}</div>
                    <div className="text-slate-500 text-xs">{u.email}</div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="text-slate-300 text-xs mb-1">
                      {used.toLocaleString()} / {limit.toLocaleString()} tokens ({pct}%)
                    </div>
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden w-40">
                      <div
                        className={`h-full rounded-full ${pct > 90 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-indigo-500"}`}
                        role="progressbar"
                        aria-label={`${u.full_name || u.email} token usage ${pct}%`}
                        {...progressProps}
                      />
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <input
                      type="number"
                      min={0}
                      placeholder={limit ? String(limit) : "Default"}
                      value={budgetEdits[u.id] ?? ""}
                      onChange={e => setBudgetEdits(prev => ({ ...prev, [u.id]: e.target.value }))}
                      className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 w-32"
                    />
                  </td>
                  <td className="px-5 py-3">
                    <button
                      onClick={() => saveUserBudget(u.id)}
                      disabled={!budgetEdits[u.id]}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 text-white text-xs font-semibold transition-colors"
                    >
                      Set
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Agent quota limits */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Agent Quota Limits</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {settings
            .filter(s => ["max_file_size_mb","max_ocr_pages_per_user","max_vision_calls","max_speech_seconds","max_image_gen"].includes(s.key))
            .map(s => (
              <div key={s.key} className="bg-slate-800 rounded-lg px-4 py-3">
                <div className="text-slate-500 text-xs mb-1">{s.description || s.key}</div>
                <div className="text-white font-semibold">{s.value}</div>
              </div>
            ))}
        </div>
        <p className="text-slate-600 text-xs mt-3">
          Edit these in the Settings page or directly in <code>admin_settings</code>.
        </p>
      </div>

      {toast && <Toast message={toast.msg} type={toast.type} onDismiss={() => setToast(null)} />}
    </div>
  );
}
