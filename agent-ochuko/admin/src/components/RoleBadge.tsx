// src/components/RoleBadge.tsx
const ROLE_STYLES: Record<string, string> = {
  superadmin: "bg-purple-500/20 text-purple-300 border border-purple-500/40",
  admin:      "bg-blue-500/20   text-blue-300   border border-blue-500/40",
  power_user: "bg-amber-500/20  text-amber-300  border border-amber-500/40",
  user:       "bg-green-500/20  text-green-300  border border-green-500/40",
  guest:      "bg-slate-500/20  text-slate-300  border border-slate-500/40",
};

interface RoleBadgeProps {
  role: string;
}

export function RoleBadge({ role }: RoleBadgeProps) {
  const cls = ROLE_STYLES[role] ?? "bg-slate-500/20 text-slate-300 border border-slate-500/40";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {role}
    </span>
  );
}
