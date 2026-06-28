// src/utils/api.ts
/**
 * Typed fetch wrapper that automatically injects the admin JWT into every
 * request to the backend /v1/admin/* routes.
 */
import { supabase } from "./supabaseClient";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

async function getAuthHeader(): Promise<{ Authorization: string }> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new Error("No active session. Please log in.");
  }
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function adminGet<T>(path: string): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BASE_URL}${path}`, { headers: { ...headers } });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function adminPatch<T>(path: string, body: unknown): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}
