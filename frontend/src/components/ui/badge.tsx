import { cn } from "../../lib/utils";

const variants: Record<string, string> = {
  default: "bg-gray-100 text-gray-700",
  blue: "bg-blue-50 text-blue-700",
  amber: "bg-amber-50 text-amber-700",
  orange: "bg-orange-50 text-orange-700",
  green: "bg-emerald-50 text-emerald-700",
  red: "bg-red-50 text-red-700",
  emerald: "bg-emerald-100 text-emerald-800 font-medium",
  pulse: "bg-blue-50 text-blue-700 animate-pulse",
};

export function Badge({ variant = "default", children, className }: {
  variant?: keyof typeof variants;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium", variants[variant] || variants.default, className)}>
      {children}
    </span>
  );
}

const STATUS_MAP: Record<string, { variant: string; label: string }> = {
  queued: { variant: "default", label: "Queued" },
  generating: { variant: "pulse", label: "Generating" },
  draft: { variant: "amber", label: "Draft" },
  reviewing: { variant: "orange", label: "Reviewing" },
  submitted: { variant: "green", label: "Submitted" },
  won: { variant: "emerald", label: "Won" },
  lost: { variant: "red", label: "Lost" },
  failed: { variant: "red", label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const config = STATUS_MAP[status] || { variant: "default", label: status };
  return <Badge variant={config.variant as any}>{config.label}</Badge>;
}

const SEVERITY_MAP: Record<string, string> = {
  high: "red",
  medium: "amber",
  low: "default",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={(SEVERITY_MAP[severity] || "default") as any}>{severity}</Badge>;
}
