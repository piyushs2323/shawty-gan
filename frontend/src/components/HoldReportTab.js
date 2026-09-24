import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2, RefreshCw, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import api, { formatApiError } from "@/lib/api";

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function HoldReportTab() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/reports/hold");
      setAccounts(data.accounts || []);
    } catch (err) {
      const msg = formatApiError(err.response?.data?.detail);
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="fade-up space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <span className="eyebrow">Payment issues</span>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-gradient mt-1">
            Hold Report
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-xl leading-relaxed">
            Scans every connected mailbox for a current "account on hold" email from Netflix — detected by its
            payment-update link, so it catches the email in any language, not just a fixed English subject.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="meter-card px-4 py-3 text-center shrink-0">
            <div className="font-mono-code text-2xl text-white">{accounts.length}</div>
            <div className="text-[11px] text-slate-500 uppercase tracking-wide">On hold</div>
            <div className="meter-fill bg-gradient-to-r from-transparent via-amber-500 to-transparent" />
          </div>
          <Button
            onClick={load}
            disabled={loading}
            variant="outline"
            size="sm"
            className="border-white/10 bg-white/5 text-slate-200 hover:bg-white/10 h-10"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div data-testid="hold-report-table" className="h24-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-slate-500">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : error ? (
          <div className="p-12 text-center text-rose-400 text-sm">{error}</div>
        ) : accounts.length === 0 ? (
          <div className="p-12 text-center">
            <AlertTriangle className="h-10 w-10 text-slate-700 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No accounts on hold</p>
            <p className="text-slate-600 text-sm mt-1">
              Every connected mailbox is clear of payment-hold emails right now.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 text-xs uppercase tracking-wide border-b border-white/10">
                <th className="px-5 py-3 font-medium">Email</th>
                <th className="px-5 py-3 font-medium">Received</th>
                <th className="px-5 py-3 font-medium text-right">Update link</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.email_norm} className="group border-b border-white/5 hover:bg-white/[0.025] transition-colors">
                  <td className="px-5 py-3.5 text-slate-200 border-l-2 border-l-transparent group-hover:border-l-amber-500/60 transition-colors">
                    <div className="font-medium">{a.email_norm}</div>
                  </td>
                  <td className="px-5 py-3.5 text-slate-400">
                    {timeAgo(a.received)}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {a.link && (
                      <a
                        href={a.link}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-400 hover:text-amber-300"
                      >
                        Open <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
