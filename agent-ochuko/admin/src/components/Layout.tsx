// src/components/Layout.tsx
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Users,
  BarChart2,
  Wallet,
  Settings,
  ScrollText,
  ShieldCheck,
  LogOut,
} from "lucide-react";
import { supabase } from "../utils/supabaseClient";

const NAV_ITEMS = [
  { to: "/users",   label: "Users",     icon: Users      },
  { to: "/usage",   label: "Usage",     icon: BarChart2  },
  { to: "/budgets", label: "Budgets",   icon: Wallet     },
  { to: "/settings",label: "Settings",  icon: Settings   },
  { to: "/audit",   label: "Audit Log", icon: ScrollText },
];

export function Layout() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    await supabase.auth.signOut();
    navigate("/", { replace: true });
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 shrink-0 border-r border-slate-800 flex flex-col bg-slate-900 justify-between">
        <div className="flex flex-col flex-1 min-h-0">
          {/* Logo */}
          <div className="h-16 flex items-center gap-3 px-5 border-b border-slate-800 shrink-0">
            <ShieldCheck size={22} className="text-indigo-400" />
            <span className="font-bold text-sm tracking-wide text-white">
              Agent Ochuko
              <span className="block text-[10px] font-normal text-slate-400 tracking-widest uppercase">
                Admin
              </span>
            </span>
          </div>

          {/* Nav */}
          <nav className="flex-1 px-3 py-4 flex flex-col justify-between overflow-y-auto min-h-0">
            <div className="space-y-1">
              {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors
                    ${isActive
                      ? "bg-indigo-600/20 text-indigo-300 border border-indigo-600/30"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    }`
                  }
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </div>

            {/* Logout button at bottom of nav list */}
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-red-400/80 hover:bg-red-950/15 hover:text-red-300 border border-transparent hover:border-red-900/30 transition-all w-full text-left mt-8 shrink-0"
            >
              <LogOut size={16} />
              Sign Out
            </button>
          </nav>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-slate-800 shrink-0">
          <p className="text-[10px] text-slate-600 uppercase tracking-widest">
            Phase 5 Control Plane
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
