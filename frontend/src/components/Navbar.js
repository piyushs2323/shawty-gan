import { Play, LogOut, Inbox, ListChecks, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const TABS = [
  { key: "mailboxes", label: "Mailboxes", icon: Inbox, testid: "nav-mailboxes-tab", adminOnly: true },
  { key: "assignments", label: "Assignments", icon: ListChecks, testid: "nav-assignments-tab", staffOnly: true },
  { key: "search", label: "Code Search", icon: Search, testid: "nav-code-search-tab", adminOnly: false },
];

export default function Navbar({ active, onChange, msConfigured }) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const isStaff = isAdmin || user?.role === "sub_admin";
  const visibleTabs = TABS.filter((t) => (!t.adminOnly || isAdmin) && (!t.staffOnly || isStaff));

  return (
    <header data-testid="nav-header" className="sticky top-0 z-40">
      <div className="glass h-16 flex items-center">
        <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2.5">
              <div className="relative h-8 w-8 rounded-lg bg-[#E50914] flex items-center justify-center shadow-[0_0_18px_rgba(229,9,20,0.45)]">
                <Play className="h-4 w-4 text-white fill-white" />
              </div>
              <span className="font-display font-extrabold text-white tracking-tight hidden sm:block">
                himawari<span className="text-[#E50914]">24</span>
              </span>
            </div>
            <nav className="flex items-center gap-1">
              {visibleTabs.map((t) => {
                const Icon = t.icon;
                const isActive = active === t.key;
                return (
                  <button
                    key={t.key}
                    data-testid={t.testid}
                    onClick={() => onChange(t.key)}
                    className={`relative flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? "text-white bg-white/[0.07]"
                        : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="hidden sm:inline">{t.label}</span>
                    {isActive && (
                      <span className="absolute left-3 right-3 -bottom-[1px] h-[2px] rounded-full bg-[#E50914] shadow-[0_0_8px_rgba(229,9,20,0.8)]" />
                    )}
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <span
              className={`hidden md:inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border ${
                msConfigured
                  ? "bg-sky-500/10 text-sky-400 border-sky-500/25"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/25"
              }`}
            >
              <span className="live-dot" />
              {msConfigured ? "Microsoft OAuth ready" : "Microsoft not configured"}
            </span>
            <span className="text-xs text-slate-500 hidden lg:block">
              {user?.email}
              {user?.role && (
                <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide border ${
                  isAdmin ? "border-emerald-500/30 text-emerald-400" : "border-slate-500/30 text-slate-400"
                }`}>
                  {user.role}
                </span>
              )}
            </span>
            <Button
              data-testid="admin-logout-button"
              onClick={logout}
              variant="ghost"
              size="sm"
              className="text-slate-400 hover:text-white hover:bg-white/5"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
      <div className="signal-line" />
    </header>
  );
}
