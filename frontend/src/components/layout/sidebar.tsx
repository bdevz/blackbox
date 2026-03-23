import { NavLink } from "react-router";
import { LayoutDashboard, FileText, FolderOpen } from "lucide-react";
import { cn } from "../../lib/utils";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/rfps", icon: FolderOpen, label: "RFPs" },
  { to: "/proposals", icon: FileText, label: "Proposals" },
];

export function Sidebar() {
  return (
    <aside className="w-56 bg-slate-900 text-white flex flex-col min-h-screen shrink-0">
      <div className="px-5 py-6 border-b border-slate-700">
        <h1 className="text-lg font-semibold tracking-tight">ConsultAdd</h1>
        <p className="text-xs text-slate-400 mt-0.5">Blackbox RFP Engine</p>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-slate-700/60 text-white font-medium"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              )
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-slate-700 text-xs text-slate-500">
        v1.0 &middot; Wave 5
      </div>
    </aside>
  );
}
