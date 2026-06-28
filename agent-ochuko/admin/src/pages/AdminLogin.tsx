// src/pages/AdminLogin.tsx
/**
 * Admin login page — 6-digit security code authentication.
 *
 * Flow:
 * 1. User enters 6-digit security code.
 * 2. Frontend POSTs code to /v1/admin/login.
 * 3. Backend verifies code and returns a signed Supabase JWT for the superadmin user.
 * 4. Frontend sets the session in Supabase client, triggering the redirect to /users.
 */
import React, { useState } from "react";
import { ShieldCheck, KeyRound } from "lucide-react";
import { supabase } from "../utils/supabaseClient";

export function AdminLogin() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCodeLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code || code.trim().length !== 6) {
      setError("Please enter a valid 6-digit code.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
      const response = await fetch(`${apiBase}/v1/admin/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ code: code.trim() }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Authentication failed.");
      }

      const data = await response.json();
      
      // Store session in Supabase client to trigger onAuthStateChange
      const { error: sessionErr } = await supabase.auth.setSession({
        access_token: data.access_token,
        refresh_token: "", // static session requires no refresh token
      });

      if (sessionErr) throw sessionErr;
    } catch (err: any) {
      setError(err.message || "Connection error. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 selection:bg-indigo-500/20">
      {/* Ambient background glow */}
      <div className="absolute w-[400px] h-[400px] bg-indigo-500/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="w-full max-w-sm relative z-10">
        <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-8 shadow-2xl">
          
          {/* Header */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-4">
              <ShieldCheck size={26} className="text-indigo-400" />
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">Admin Dashboard</h1>
            <p className="text-slate-400 text-xs mt-1 font-medium tracking-wide">
              Agent Ochuko Control Plane
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleCodeLogin} className="space-y-5">
            <div className="space-y-2">
              <label htmlFor="security-code" className="text-[11px] font-bold text-slate-400 tracking-wider uppercase">
                Security Code
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                  <KeyRound size={16} />
                </div>
                <input
                  id="security-code"
                  type="text"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="••••••"
                  className="w-full h-12 bg-slate-950/80 border border-slate-800 rounded-xl pl-10 pr-4 text-center text-lg font-mono tracking-[0.4em] text-indigo-300 placeholder-slate-700 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/10 transition"
                  disabled={loading}
                  autoComplete="one-time-code"
                />
              </div>
            </div>

            {error && (
              <div className="p-3 bg-red-950/30 border border-red-900/40 rounded-xl text-xs text-red-300 text-center leading-relaxed">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || code.length !== 6}
              className="w-full h-12 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs tracking-wider uppercase rounded-xl flex items-center justify-center transition-all disabled:opacity-30 active:scale-[0.98] shadow-lg shadow-indigo-600/10"
            >
              {loading ? (
                <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                "Verify & Enter"
              )}
            </button>
          </form>

          <p className="text-center text-[10px] text-slate-600 font-semibold tracking-wider uppercase mt-6">
            Authorized Personnel Only
          </p>

        </div>
      </div>
    </div>
  );
}
