import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Search, Loader2, Copy, Check, ExternalLink, KeyRound,
  MailX, PlugZap, Clock, AlertTriangle, ShieldCheck, Lock, Tv, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api, { formatApiError } from "@/lib/api";

const REASON_UI = {
  not_connected: { icon: PlugZap, color: "text-amber-400", title: "Mailbox not connected", desc: "Connect this Outlook mailbox in the Mailboxes tab first." },
  needs_reconnect: { icon: AlertTriangle, color: "text-rose-400", title: "Needs reconnect", desc: "The Microsoft token was revoked or expired. Reconnect the mailbox." },
  empty: { icon: MailX, color: "text-slate-400", title: "No matching email found", desc: "No recent Netflix email matched this category in the inbox." },
  not_configured: { icon: AlertTriangle, color: "text-amber-400", title: "Gmail IMAP not configured", desc: "Set GMAIL_IMAP_USER and GMAIL_IMAP_PASSWORD to use the Gmail path." },
  throttled: { icon: Clock, color: "text-amber-400", title: "Microsoft throttled the request", desc: "Graph returned 429. Please retry in a few seconds." },
  error: { icon: AlertTriangle, color: "text-rose-400", title: "Fetch error", desc: "Something went wrong while reading the mailbox." },
};

// One icon per category so the dropdown reads at a glance instead of as a
// wall of plain text.
const CATEGORY_ICONS = {
  login_code: KeyRound,
  verification_code: ShieldCheck,
  household: Users,
  password_reset: Lock,
  tv_login: Tv,
};

export default function CodeSearchTab() {
  const [assignments, setAssignments] = useState([]);
  const [categories, setCategories] = useState([]);
  const [emailNorm, setEmailNorm] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([api.get("/assignments"), api.get("/categories")]);
      setAssignments(a.data);
      setCategories(c.data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async () => {
    if (!emailNorm || !category) {
      toast.error("Pick an email and a category");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post("/search", { email_norm: emailNorm, category });
      setResult(data);
      if (!data.found) {
        const ui = REASON_UI[data.reason];
        if (ui) toast.message(ui.title);
      }
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const copy = (val) => {
    navigator.clipboard.writeText(val);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="fade-up space-y-6 max-w-4xl">
      <div>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-white">Code Search</h1>
        <p className="text-sm text-slate-400 mt-2 max-w-xl leading-relaxed">
          Pick an assigned Netflix email and a category. We route to the right provider, read the inbox and extract the
          code or link.
        </p>
      </div>

      <div className="h24-card p-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500 uppercase tracking-wide">Netflix email</label>
            <Select value={emailNorm} onValueChange={setEmailNorm}>
              <SelectTrigger data-testid="email-assignment-select" className="bg-black/40 border-white/10 text-slate-100">
                <SelectValue placeholder="Select email…" />
              </SelectTrigger>
              <SelectContent>
                {assignments.map((a) => (
                  <SelectItem key={a.email_norm} value={a.email_norm}>
                    {a.email_norm}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500 uppercase tracking-wide">Category</label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger data-testid="category-select" className="bg-black/40 border-white/10 text-slate-100">
                <SelectValue placeholder="Select category…">
                  {(() => {
                    const cat = categories.find((c) => c.key === category);
                    if (!cat) return null;
                    const Icon = CATEGORY_ICONS[cat.key] || KeyRound;
                    return (
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-[#E50914]" />
                        {cat.label}
                      </span>
                    );
                  })()}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {categories.map((c) => {
                  const Icon = CATEGORY_ICONS[c.key] || KeyRound;
                  return (
                    <SelectItem key={c.key} value={c.key}>
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-[#E50914]" />
                        {c.label}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
        <Button
          data-testid="fetch-netflix-code-button"
          onClick={run}
          disabled={loading}
          className="w-full h-11 bg-[#E50914] hover:bg-[#c40810] text-white font-semibold"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Search className="h-4 w-4 mr-2" />}
          Fetch code
        </Button>
      </div>

      {result && result.found && (
        <div data-testid="parsed-result-card" className="h24-card p-8 fade-up border-emerald-500/20 shadow-[0_0_35px_rgba(16,185,129,0.08)]">
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium mb-5">
            <KeyRound className="h-4 w-4" /> Result found
            {result.country && (
              <span
                data-testid="parsed-country-badge"
                className="inline-flex items-center gap-1.5 text-xs text-slate-300 bg-white/5 border border-white/10 rounded-full px-2 py-0.5"
                title={result.country.code ? `Region: ${result.country.code}` : "Region detected"}
              >
                {result.country.flag && <span className="text-sm leading-none">{result.country.flag}</span>}
                <span>{result.country.country || result.country.code || "Region detected"}</span>
              </span>
            )}
            <span className="ml-auto text-xs text-slate-500 font-normal">
              via {result.provider === "outlook_graph" ? "Microsoft Graph" : "Gmail IMAP"}
            </span>
          </div>

          {result.code && (
            <div className="mb-5">
              <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Extracted code</div>
              <div className="flex items-center gap-3">
                <div
                  data-testid="parsed-code-display"
                  className="font-mono-code text-3xl sm:text-4xl tracking-[0.3em] font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 rounded-xl px-6 py-4"
                >
                  {result.code}
                </div>
                <Button
                  data-testid="copy-code-button"
                  onClick={() => copy(result.code)}
                  variant="outline"
                  size="icon"
                  className="h-12 w-12 border-white/10 bg-white/5 hover:bg-white/10"
                >
                  {copied ? <Check className="h-5 w-5 text-emerald-400" /> : <Copy className="h-5 w-5 text-slate-300" />}
                </Button>
              </div>
            </div>
          )}

          {result.link && (
            <div className="mb-5">
              <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Action link</div>
              <a
                data-testid="parsed-link-display"
                href={result.link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-sky-400 hover:text-sky-300 text-sm break-all bg-sky-500/5 border border-sky-500/20 rounded-lg px-4 py-3"
              >
                <ExternalLink className="h-4 w-4 shrink-0" />
                {result.link}
              </a>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm pt-4 border-t border-white/10">
            <div>
              <div className="text-xs text-slate-500 mb-1">Subject</div>
              <div className="text-slate-200">{result.subject || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">From</div>
              <div className="text-slate-300">{result.from || "—"}</div>
            </div>
            <div className="sm:col-span-2">
              <div className="text-xs text-slate-500 mb-1">Received</div>
              <div data-testid="parsed-timestamp-display" className="text-slate-300 font-mono-code text-xs">
                {result.received || "—"}
              </div>
            </div>
          </div>

          {result.snippet && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <div className="text-xs text-slate-500 mb-1">Snippet</div>
              <p className="text-slate-400 text-xs leading-relaxed">{result.snippet}</p>
            </div>
          )}
        </div>
      )}

      {result && !result.found && (() => {
        const ui = REASON_UI[result.reason] || REASON_UI.error;
        const Icon = ui.icon;
        return (
          <div data-testid="parsed-result-card" className="h24-card p-8 text-center fade-up">
            <Icon className={`h-10 w-10 mx-auto mb-3 ${ui.color}`} />
            <div className="text-slate-200 font-medium">{ui.title}</div>
            <p className="text-slate-500 text-sm mt-1">{ui.desc}</p>
          </div>
        );
      })()}
    </div>
  );
}
