// src/pages/Users.tsx
import { useEffect, useState, useCallback } from "react";
import { Search, ShieldOff, Pause, Play, ChevronLeft, ChevronRight, Users as UsersIcon } from "lucide-react";
import { adminGet, adminPatch } from "../utils/api";
import { ConfirmModal } from "../components/ConfirmModal";
import { Toast } from "../components/Toast";

interface TokenBudget {
  tokens_used: number;
  budget_limit: number;
}

interface UserRow {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  last_seen: string | null;
  google_sub: string;
  token_budgets: TokenBudget | null;
  agent_calls_this_month: number;
  total_tokens_used?: number;
}

interface UsersResponse {
  users: UserRow[];
  page: number;
  page_size: number;
}

interface SettingsResponse {
  settings: Array<{ key: string; value: string }>;
}

const VALID_ROLES = ["guest", "user", "power_user", "admin", "superadmin"];

export function Users() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [filteredUsers, setFilteredUsers] = useState<UserRow[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [registrationLimit, setRegistrationLimit] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // Confirm modal state
  const [confirm, setConfirm] = useState<{
    title: string; message: string; danger?: boolean; label: string; action: () => Promise<void>;
  } | null>(null);

  const fetchUsers = useCallback(async (p: number) => {
    setLoading(true);
    try {
      // Fetch users and registration limit in parallel on page 1
      const promises: [Promise<UsersResponse>, Promise<SettingsResponse> | null] = [
        adminGet<UsersResponse>(`/v1/admin/users?page=${p}&page_size=50`),
        p === 1 ? adminGet<SettingsResponse>("/v1/admin/settings") : null,
      ];
      const [data, settingsData] = await Promise.all(promises);
      setUsers(data.users);
      setHasMore(data.users.length === 50);

      // Approximate total: page * page_size if full page, else offset + count
      const approx = (p - 1) * 50 + data.users.length;
      setTotalCount(prev => p === 1 ? approx : Math.max(prev, approx));

      if (settingsData) {
        const limitSetting = settingsData.settings.find(s => s.key === "registration_limit");
        if (limitSetting) setRegistrationLimit(parseInt(limitSetting.value, 10));
      }
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(page); }, [page, fetchUsers]);

  useEffect(() => {
    const q = search.toLowerCase();
    setFilteredUsers(
      q ? users.filter(u =>
        u.email?.toLowerCase().includes(q) ||
        u.full_name?.toLowerCase().includes(q)
      ) : users
    );
  }, [search, users]);

  const doAction = async (action: () => Promise<void>) => {
    try {
      await action();
      setToast({ msg: "Action completed successfully.", type: "success" });
      fetchUsers(page);
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    }
    setConfirm(null);
  };

  const promptBlock = (u: UserRow) =>
    setConfirm({
      title: "Block user permanently",
      message: `Block ${u.email}? This writes their Google ID to the blocklist — they cannot log in even with a new email.`,
      danger: true,
      label: "Block permanently",
      action: () => adminPatch(`/v1/admin/users/${u.id}/block`, { google_sub: u.google_sub }),
    });

  const promptSuspend = (u: UserRow) =>
    setConfirm({
      title: "Suspend user",
      message: `Suspend ${u.email}? They will be unable to log in until re-activated.`,
      danger: true,
      label: "Suspend",
      action: () => adminPatch(`/v1/admin/users/${u.id}/suspend`, {}),
    });

  const handleActivate = (u: UserRow) =>
    doAction(() => adminPatch(`/v1/admin/users/${u.id}/activate`, {}));

  const handleRoleChange = (u: UserRow, role: string) =>
    doAction(() => adminPatch(`/v1/admin/users/${u.id}/role`, { role }));

  const fmt = (date: string | null) =>
    date ? new Date(date).toLocaleDateString() : "—";

  const renderLastSeen = (lastSeenStr: string | null) => {
    if (!lastSeenStr) return <span className="text-slate-500">—</span>;
    const lastSeen = new Date(lastSeenStr);
    const now = new Date();
    const diffMs = now.getTime() - lastSeen.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 5) {
      return (
        <div className="flex items-center gap-1.5 text-green-400 font-medium select-none">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
          </span>
          Active Now
        </div>
      );
    }

    if (diffMins < 60) {
      return <span className="text-slate-300">{diffMins}m ago</span>;
    }

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) {
      return <span className="text-slate-300">{diffHours}h ago</span>;
    }

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) {
      return <span className="text-slate-400">{diffDays}d ago</span>;
    }

    return <span className="text-slate-400">{lastSeen.toLocaleDateString()}</span>;
  };

  return (
    <div className="p-6">
      {/* Header row */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Users</h1>
          <p className="text-slate-400 text-sm">Manage registered accounts, roles, and access.</p>
        </div>

        {/* Registration count widget */}
        {registrationLimit !== null && (
          <div className="flex items-center gap-3 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3">
            <div className="relative w-9 h-9">
              <svg className="w-9 h-9 -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1e293b" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15.9" fill="none"
                  stroke={totalCount >= registrationLimit ? "#ef4444" : totalCount / registrationLimit > 0.8 ? "#f59e0b" : "#6366f1"}
                  strokeWidth="3"
                  strokeDasharray={`${Math.min(100, Math.round((totalCount / registrationLimit) * 100))} 100`}
                  strokeLinecap="round"
                />
              </svg>
              <UsersIcon size={12} className="absolute inset-0 m-auto text-slate-400" />
            </div>
            <div>
              <div className="text-white font-bold text-sm leading-none">
                {totalCount} <span className="text-slate-500 font-normal">/ {registrationLimit}</span>
              </div>
              <div className="text-slate-500 text-xs mt-0.5">registered users</div>
            </div>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-sm">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
          placeholder="Search by name or email…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left">Name / Email</th>
                <th className="px-4 py-3 text-left">Role</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Tokens Used</th>
                <th className="px-4 py-3 text-left">Agent Calls</th>
                <th className="px-4 py-3 text-left">Last Seen</th>
                <th className="px-4 py-3 text-left">Joined</th>
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    Loading…
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    No users found.
                  </td>
                </tr>
              ) : (
                filteredUsers.map(u => (
                  <tr key={u.id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200">{u.full_name || "—"}</div>
                      <div className="text-slate-500 text-xs">{u.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        aria-label={`Change role for ${u.full_name || u.email}`}
                        value={u.role}
                        onChange={e => handleRoleChange(u, e.target.value)}
                        className="bg-transparent text-sm focus:outline-none cursor-pointer"
                      >
                        {VALID_ROLES.map(r => (
                          <option key={r} value={r} className="bg-slate-800">{r}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        u.is_active
                          ? "bg-green-500/15 text-green-400"
                          : "bg-red-500/15 text-red-400"
                      }`}>
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      <div className="font-medium text-slate-200">
                        {(u.total_tokens_used ?? 0).toLocaleString()}
                      </div>
                      <div className="text-slate-500 text-xs">
                        {u.token_budgets
                          ? `Today: ${u.token_budgets.tokens_used.toLocaleString()} / ${u.token_budgets.budget_limit.toLocaleString()}`
                          : "Today: —"}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {(u.agent_calls_this_month ?? 0).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">{renderLastSeen(u.last_seen)}</td>
                    <td className="px-4 py-3 text-slate-400">{fmt(u.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {u.is_active ? (
                          <button
                            onClick={() => promptSuspend(u)}
                            title="Suspend"
                            className="p-1.5 rounded-lg hover:bg-amber-500/10 text-amber-400 transition-colors"
                          >
                            <Pause size={14} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleActivate(u)}
                            title="Activate"
                            className="p-1.5 rounded-lg hover:bg-green-500/10 text-green-400 transition-colors"
                          >
                            <Play size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => promptBlock(u)}
                          title="Block permanently"
                          className="p-1.5 rounded-lg hover:bg-red-500/10 text-red-400 transition-colors"
                        >
                          <ShieldOff size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
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
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Confirm modal */}
      {confirm && (
        <ConfirmModal
          isOpen
          title={confirm.title}
          message={confirm.message}
          danger={confirm.danger}
          confirmLabel={confirm.label}
          onConfirm={() => doAction(confirm.action)}
          onCancel={() => setConfirm(null)}
        />
      )}

      {/* Toast */}
      {toast && (
        <Toast message={toast.msg} type={toast.type} onDismiss={() => setToast(null)} />
      )}
    </div>
  );
}
