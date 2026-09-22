import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Plug, Unplug, RefreshCw, Mail, CheckCircle2, AlertTriangle,
  Loader2, ShieldAlert, Inbox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api, { formatApiError } from "@/lib/api";

function StatusBadge({ status }) {
  if (status === "connected") {
    return (
      <span
        data-testid="mailbox-card-status-connected"
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
      >
        <CheckCircle2 className="h-3.5 w-3.5" /> Connected
      </span>
    );
  }
  if (status === "needs_reconnect") {
    return (
      <span
        data-testid="mailbox-card-status-reconnect"
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30 animate-pulse"
      >
        <AlertTriangle className="h-3.5 w-3.5" /> Needs Reconnect
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/30">
      Not connected
    </span>
  );
}

export default function MailboxesTab({ status, refreshKey, onChanged }) {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/assignments");
      setAssignments(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const connect = async (email_norm) => {
    if (!status.microsoft_configured) {
      toast.error("Microsoft OAuth is not configured yet. Add MS_CLIENT_ID and MS_CLIENT_SECRET.");
      return;
    }
    setBusy(email_norm);
    try {
      const { data } = await api.get("/mailboxes/connect", { params: { email_norm } });
      window.location.href = data.auth_url;
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setBusy(null);
    }
  };

  const disconnect = async (email_norm) => {
    setBusy(email_norm);
    try {
      await api.post(`/mailboxes/${encodeURIComponent(email_norm)}/disconnect`);
      toast.success("Mailbox disconnected");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(null);
    }
  };

  const outlookBoxes = assignments.filter((a) => a.provider === "outlook_graph");
  const connectedCount = outlookBoxes.filter((a) => a.mailbox_status === "connected").length;

  return (
    <div className="fade-up space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-white">Mailboxes</h1>
          <p className="text-sm text-slate-400 mt-2 max-w-xl leading-relaxed">
            Connect each personal Outlook / Hotmail inbox once via Microsoft. We store an encrypted refresh token and
            read Netflix codes directly through Microsoft Graph — no forwarding.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="h24-card px-4 py-3 text-center">
            <div className="font-mono-code text-2xl text-emerald-400">{connectedCount}</div>
            <div className="text-[11px] text-slate-500 uppercase tracking-wide">Connected</div>
          </div>
          <div className="h24-card px-4 py-3 text-center">
            <div className="font-mono-code text-2xl text-sky-400">{outlookBoxes.length}</div>
            <div className="text-[11px] text-slate-500 uppercase tracking-wide">Outlook</div>
          </div>
        </div>
      </div>

      {!status.microsoft_configured && (
        <div className="h24-card p-4 border-amber-500/30 bg-amber-500/5 flex items-start gap-3">
          <ShieldAlert className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-200/90">
            <span className="font-semibold">Microsoft OAuth not configured.</span> Add{" "}
            <code className="font-mono-code text-xs">MS_CLIENT_ID</code> and{" "}
            <code className="font-mono-code text-xs">MS_CLIENT_SECRET</code> to the backend .env, then restart. Redirect
            URI to register: <code className="font-mono-code text-xs break-all">{status.redirect_uri}</code>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : outlookBoxes.length === 0 ? (
        <div className="h24-card p-12 text-center">
          <Inbox className="h-10 w-10 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No Outlook assignments yet.</p>
          <p className="text-slate-600 text-sm mt-1">Add an email in the Assignments tab with provider “Outlook (Graph)”.</p>
        </div>
      ) : (
        <div data-testid="mailbox-list" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {outlookBoxes.map((a) => {
            const st = a.mailbox_status || "none";
            const isBusy = busy === a.email_norm;
            return (
              <div key={a.email_norm} className="h24-card p-6 flex flex-col gap-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-10 w-10 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center shrink-0">
                      <Mail className="h-5 w-5 text-sky-400" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-slate-100 font-medium truncate">{a.email_norm}</div>
                      {a.mailbox_email && (
                        <div className="text-xs text-slate-500 truncate">Inbox: {a.mailbox_email}</div>
                      )}
                    </div>
                  </div>
                  <StatusBadge status={st} />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  {st === "connected" ? (
                    <>
                      <Button
                        data-testid="reconnect-outlook-button"
                        onClick={() => connect(a.email_norm)}
                        disabled={isBusy}
                        variant="outline"
                        size="sm"
                        className="border-white/10 bg-white/5 text-slate-200 hover:bg-white/10 flex-1"
                      >
                        <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Re-consent
                      </Button>
                      <Button
                        data-testid="disconnect-mailbox-button"
                        onClick={() => disconnect(a.email_norm)}
                        disabled={isBusy}
                        variant="outline"
                        size="sm"
                        className="border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
                      >
                        {isBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                      </Button>
                    </>
                  ) : (
                    <Button
                      data-testid={st === "needs_reconnect" ? "reconnect-outlook-button" : "connect-outlook-button"}
                      onClick={() => connect(a.email_norm)}
                      disabled={isBusy}
                      size="sm"
                      className={`flex-1 font-semibold ${
                        st === "needs_reconnect"
                          ? "bg-rose-600 hover:bg-rose-700 text-white"
                          : "bg-[#0078D4] hover:bg-[#106ebe] text-white"
                      }`}
                    >
                      {isBusy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <Plug className="h-4 w-4 mr-1.5" />
                          {st === "needs_reconnect" ? "Reconnect Outlook" : "Connect Outlook"}
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
