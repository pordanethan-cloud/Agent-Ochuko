// src/components/Layout.tsx
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Users,
  BarChart2,
  Wallet,
  Settings,
  ScrollText,
  LogOut,
  Menu,
} from "lucide-react";
import { supabase } from "../utils/supabaseClient";

const NAV_ITEMS = [
  { to: "/users",   label: "Users",     icon: Users      },
  { to: "/usage",   label: "Usage",     icon: BarChart2  },
  { to: "/budgets", label: "Budgets",   icon: Wallet     },
  { to: "/settings",label: "Settings",  icon: Settings   },
  { to: "/audit",   label: "Audit Log", icon: ScrollText },
];

/** Shared sidebar content — rendered inside both the desktop rail and the mobile drawer. */
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const handleLogout = async () => {
    try {
      const keysToRemove: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key && (key.startsWith('sb-') || key.includes('supabase'))) {
          keysToRemove.push(key)
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key))
      await supabase.auth.signOut();
    } catch (error) {
      console.error("Error signing out from admin:", error);
    } finally {
      window.location.href = "/";
    }
  };

  return (
    <>
      <div className="flex flex-col flex-1 min-h-0">
        {/* Logo */}
        <div className="h-16 flex items-center gap-3 px-5 border-b border-slate-800 shrink-0">
          <div className="w-6 h-6 rounded overflow-hidden border border-slate-700 bg-slate-950 shrink-0">
            <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />
          </div>
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
                onClick={onNavigate}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm transition-colors
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
            className="flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm text-red-400/80 hover:bg-red-950/15 hover:text-red-300 border border-transparent hover:border-red-900/30 transition-all w-full text-left mt-8 shrink-0"
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
    </>
  );
}

export function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Desktop sidebar (lg and up) */}
      <aside className="hidden lg:flex w-60 shrink-0 border-r border-slate-800 flex-col bg-slate-900 justify-between">
        <SidebarContent />
      </aside>

      {/* Mobile top bar (below lg) */}
      <header
        className="lg:hidden fixed top-0 left-0 right-0 z-40 h-14 flex items-center gap-3 px-3
          bg-slate-900/95 backdrop-blur-md border-b border-slate-800
          pt-[env(safe-area-inset-top)]"
      >
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation menu"
          className="p-2 -ml-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg
            text-slate-300 hover:bg-slate-800 active:scale-95 transition touch-manipulation"
        >
          <Menu size={22} />
        </button>
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded overflow-hidden border border-slate-700 bg-slate-950 shrink-0">
            <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />
          </div>
          <span className="font-bold text-sm tracking-wide text-white truncate">
            Agent Ochuko
            <span className="block text-[9px] font-normal text-slate-400 tracking-widest uppercase leading-tight">
              Admin
            </span>
          </span>
        </div>
      </header>

      {/* Mobile drawer backdrop */}
      {drawerOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile slide-in drawer (below lg) */}
      <aside
        className={`lg:hidden fixed top-0 left-0 bottom-0 z-50 w-64 max-w-[85vw] flex flex-col justify-between
          bg-slate-900 border-r border-slate-800 shadow-2xl
          pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]
          transition-transform duration-300 ease-out ${
            drawerOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        aria-label="Navigation menu"
      >
        <SidebarContent onNavigate={() => setDrawerOpen(false)} />
      </aside>

      {/* Main content — offset below the mobile top bar */}
      <main className="flex-1 overflow-y-auto pt-14 lg:pt-0 pb-[env(safe-area-inset-bottom)]">
        <Outlet />
      </main>
    </div>
  );
}
