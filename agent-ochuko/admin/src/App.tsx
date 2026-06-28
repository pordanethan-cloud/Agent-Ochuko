// src/App.tsx
/**
 * Admin app root.
 *
 * Auth flow:
 * 1. On load, check Supabase session.
 * 2. If no session → show AdminLogin.
 * 3. If session but role not in {admin, superadmin} → redirect to /not-authorized.
 * 4. OAuth callback (/#access_token=…) → exchangeCodeForSession, then re-check role.
 * 5. Admins see the sidebar layout with all pages.
 */
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
} from "react-router-dom";
import { supabase } from "./utils/supabaseClient";
import { Layout } from "./components/Layout";
import { AdminLogin } from "./pages/AdminLogin";
import { NotAuthorized } from "./pages/NotAuthorized";
import { Users } from "./pages/Users";
import { Usage } from "./pages/Usage";
import { Budgets } from "./pages/Budgets";
import { Settings } from "./pages/Settings";
import { AuditLog } from "./pages/AuditLog";

const ADMIN_ROLES = new Set(["admin", "superadmin"]);

type AuthState = "loading" | "unauthenticated" | "unauthorized" | "authorized";

function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    // Exchange hash fragment tokens for a proper session
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) {
        navigate("/", { replace: true });
        return;
      }
      let role =
        session.user.app_metadata?.role ||
        session.user.user_metadata?.role;
      
      if (!role || !ADMIN_ROLES.has(role)) {
        const { data } = await supabase
          .from("profiles")
          .select("role")
          .eq("id", session.user.id)
          .single();
        if (data?.role) {
          role = data.role;
        }
      }

      if (role && ADMIN_ROLES.has(role)) {
        navigate("/users", { replace: true });
      } else {
        navigate("/not-authorized", { replace: true });
      }
    });
  }, [navigate]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-sm">
      Verifying credentials…
    </div>
  );
}

export default function App() {
  const [authState, setAuthState] = useState<AuthState>("loading");

  useEffect(() => {
    const checkSession = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        setAuthState("unauthenticated");
        return;
      }
      let role =
        session.user.app_metadata?.role ||
        session.user.user_metadata?.role;
      
      if (!role || !ADMIN_ROLES.has(role)) {
        const { data } = await supabase
          .from("profiles")
          .select("role")
          .eq("id", session.user.id)
          .single();
        if (data?.role) {
          role = data.role;
        }
      }
      setAuthState(role && ADMIN_ROLES.has(role) ? "authorized" : "unauthorized");
    };

    checkSession();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (!session) {
        setAuthState("unauthenticated");
        return;
      }
      let role =
        session.user.app_metadata?.role ||
        session.user.user_metadata?.role;
      
      if (!role || !ADMIN_ROLES.has(role)) {
        const { data } = await supabase
          .from("profiles")
          .select("role")
          .eq("id", session.user.id)
          .single();
        if (data?.role) {
          role = data.role;
        }
      }
      setAuthState(role && ADMIN_ROLES.has(role) ? "authorized" : "unauthorized");
    });

    return () => subscription.unsubscribe();
  }, []);

  if (authState === "loading") {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* OAuth callback — must be accessible before auth check */}
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/not-authorized" element={<NotAuthorized />} />

        {/* Unauthenticated */}
        {authState === "unauthenticated" && (
          <>
            <Route path="/" element={<AdminLogin />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}

        {/* Authenticated but wrong role */}
        {authState === "unauthorized" && (
          <Route path="*" element={<NotAuthorized />} />
        )}

        {/* Fully authorized */}
        {authState === "authorized" && (
          <>
            <Route path="/" element={<Navigate to="/users" replace />} />
            <Route element={<Layout />}>
              <Route path="/users"    element={<Users />} />
              <Route path="/usage"    element={<Usage />} />
              <Route path="/budgets"  element={<Budgets />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/audit"    element={<AuditLog />} />
            </Route>
            <Route path="*" element={<Navigate to="/users" replace />} />
          </>
        )}
      </Routes>
    </BrowserRouter>
  );
}
