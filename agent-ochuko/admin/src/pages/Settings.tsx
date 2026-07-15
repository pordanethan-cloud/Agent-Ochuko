// src/pages/Settings.tsx
import { useEffect, useState, useCallback } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
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



// Keys written to Azure App Configuration via PATCH /v1/admin/settings/appcfg
const APPCFG_MODEL_KEYS = [
  "THINK_MODEL_DEPLOYMENT",
  "SOLVE_MODEL_DEPLOYMENT",
  "NANO_MODEL_DEPLOYMENT",
  "COMPACTION_MODEL_DEPLOYMENT",
];

const APPCFG_PROMPT_KEYS = [
  "THINK_PROMPT",
  "SOLVE_PROMPT",
  "DISCUSS_PROMPT",
  "NANO_PROMPT",
];

export function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [promptsOpen, setPromptsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminGet<SettingsResponse>("/v1/admin/settings");
      const map: Record<string, string> = {};
      data.settings.forEach(s => { map[s.key] = s.value; });
      setSettings(map);
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const val = (key: string) => edits[key] ?? settings[key] ?? "";
  const set = (key: string, v: string) => setEdits(prev => ({ ...prev, [key]: v }));

  // Saves keys (e.g. registration_limit, registration_open, maintenance_mode, max_file_size_mb, etc.)
  // to Supabase admin_settings via PATCH /v1/admin/settings
  const saveSupabaseKeys = async (keys: string[]) => {
    const updates: Record<string, string> = {};
    keys.forEach(k => { updates[k] = val(k); });
    setSaving("supabase");
    try {
      await adminPatch("/v1/admin/settings", { updates });
      setToast({ msg: "Settings saved.", type: "success" });
      load();
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    } finally {
      setSaving(null);
    }
  };

  const saveAppCfgKeys = async (keys: string[]) => {
    const updates: Record<string, string> = {};
    keys.forEach(k => { updates[k] = val(k); });
    setSaving("appcfg");
    try {
      await adminPatch("/v1/admin/settings/appcfg", { updates });
      setToast({ msg: "Azure App Configuration updated. Changes are live immediately.", type: "success" });
    } catch (e: unknown) {
      setToast({ msg: (e as Error).message, type: "error" });
    } finally {
      setSaving(null);
    }
  };

  if (loading) return (
    <div className="p-6 flex items-center justify-center h-64 text-slate-500 text-sm">Loading…</div>
  );



  return (
    <div className="p-6 space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Settings</h1>
        <p className="text-slate-400 text-sm">
          Control registration, maintenance mode, and model deployments — all without redeploying.
        </p>
      </div>

      {/* Registration & maintenance */}
      <Section title="Registration & Access">
        {val("maintenance_mode") === "true" && (
          <div className="mb-4 p-3 bg-amber-900/30 border border-amber-700/40 rounded-lg text-amber-300 text-xs">
            Warning: Maintenance mode is ON — all non-admin requests return 503.
          </div>
        )}
        <Field label="Registration Cap" hint="Max registered users allowed.">
          <input
            type="number" min={0}
            aria-label="Registration cap"
            value={val("registration_limit")}
            onChange={e => set("registration_limit", e.target.value)}
            className={inputCls}
          />
        </Field>
        <Field label="Registration Open" hint="Allow new signups.">
          <Toggle
            enabled={val("registration_open") === "true"}
            onToggle={() => set("registration_open", val("registration_open") === "true" ? "false" : "true")}
          />
        </Field>
        <Field label="Maintenance Mode" hint="Block all non-admin traffic.">
          <Toggle
            enabled={val("maintenance_mode") === "true"}
            onToggle={() => set("maintenance_mode", val("maintenance_mode") === "true" ? "false" : "true")}
          />
        </Field>
        <SaveBtn
          onClick={() => saveSupabaseKeys(["registration_limit","registration_open","maintenance_mode"])}
          loading={saving === "supabase"}
        />
      </Section>

      {/* Model deployments */}
      <Section title="Active Model Deployments" hint="Written to Azure App Configuration — live immediately.">
        {APPCFG_MODEL_KEYS.map(k => (
          <Field key={k} label={k.replace(/_/g, " ")}>
            <input
              type="text"
              aria-label={k.replace(/_/g, " ")}
              value={val(k)}
              onChange={e => set(k, e.target.value)}
              className={inputCls}
            />
          </Field>
        ))}
        <SaveBtn
          onClick={() => saveAppCfgKeys(APPCFG_MODEL_KEYS)}
          loading={saving === "appcfg"}
          label="Save to App Config"
        />
      </Section>

      {/* System prompts (collapsible) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-5 py-4 text-sm font-semibold text-slate-300 hover:bg-slate-800/50 transition-colors"
          onClick={() => setPromptsOpen(o => !o)}
        >
          <span>System Prompts <span className="text-slate-500 font-normal">(Advanced)</span></span>
          {promptsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {promptsOpen && (
          <div className="px-5 pb-5 space-y-4 border-t border-slate-800 pt-4">
            <p className="text-slate-500 text-xs">
              Written to Azure App Configuration — takes effect immediately, no redeploy.
            </p>
            {APPCFG_PROMPT_KEYS.map(k => (
              <div key={k}>
                <label className="block text-xs text-slate-400 mb-1" htmlFor={`prompt-${k}`}>{k}</label>
                <textarea
                  id={`prompt-${k}`}
                  rows={4}
                  value={val(k)}
                  onChange={e => set(k, e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 font-mono resize-y"
                />
              </div>
            ))}
            <SaveBtn
              onClick={() => saveAppCfgKeys(APPCFG_PROMPT_KEYS)}
              loading={saving === "appcfg"}
              label="Save Prompts to App Config"
            />
          </div>
        )}
      </div>

      {toast && <Toast message={toast.msg} type={toast.type} onDismiss={() => setToast(null)} />}
    </div>
  );
}

// Sub-components
function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-300">{title}</h2>
        {hint && <p className="text-slate-600 text-xs mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="text-sm text-slate-300">{label}</div>
        {hint && <div className="text-xs text-slate-600">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ enabled, onToggle, label }: { enabled: boolean; onToggle: () => void; label?: string }) {
  return (
    <button
      role="switch"
      aria-checked={enabled ? "true" : "false"}
      aria-label={label ?? (enabled ? "Enabled" : "Disabled")}
      onClick={onToggle}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${enabled ? "bg-indigo-600" : "bg-slate-700"}`}
    >
      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-4.5" : "translate-x-0.5"}`} />
    </button>
  );
}

function SaveBtn({ onClick, loading, label = "Save" }: { onClick: () => void; loading: boolean; label?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
    >
      {loading ? "Saving…" : label}
    </button>
  );
}

const inputCls = "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 w-52";
