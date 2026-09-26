import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Inbox, Loader2, ExternalLink, MailOpen, Mail, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
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

export default function InboxTab() {
  const [assignments, setAssignments] = useState([]);
  const [emailNorm, setEmailNorm] = useState("");
  const [messages, setMessages] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingList, setLoadingList] = useState(true);

  const loadAssignments = useCallback(async () => {
    setLoadingList(true);
    try {
      const { data } = await api.get("/assignments");
      const connected = data.filter((a) => a.provider === "outlook_graph" && a.mailbox_status === "connected");
      setAssignments(connected);
      if (connected.length > 0) setEmailNorm((cur) => cur || connected[0].email_norm);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  const loadInbox = useCallback(async () => {
    if (!emailNorm) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/mailboxes/${encodeURIComponent(emailNorm)}/inbox`);
      if (data.status === "ok") {
        setMessages(data.messages || []);
      } else {
        setMessages([]);
        if (data.status === "needs_reconnect") toast.error("This mailbox needs to be reconnected.");
        else if (data.status === "not_connected") toast.error("This mailbox isn't connected yet.");
      }
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [emailNorm]);

  useEffect(() => {
    if (emailNorm) loadInbox();
  }, [emailNorm, loadInbox]);

  return (
    <div className="fade-up space-y-6 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <span className="eyebrow">Live view</span>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-gradient mt-1">
            Inbox
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-xl leading-relaxed">
            See what's actually arriving in a connected mailbox, straight from Outlook — not filtered to any one
            category.
          </p>
        </div>
      </div>

      <div className="h24-card p-5 flex flex-col sm:flex-row gap-3 sm:items-end">
        <div className="flex-1 space-y-1.5">
          <label className="text-xs text-slate-500 uppercase tracking-wide">Mailbox</label>
          <Select value={emailNorm} onValueChange={setEmailNorm} disabled={loadingList || assignments.length === 0}>
            <SelectTrigger data-testid="inbox-mailbox-select" className="bg-black/40 border-white/10 text-slate-100 h-10">
              <SelectValue placeholder={assignments.length === 0 ? "No connected mailboxes" : "Select mailbox…"} />
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
        <Button
          onClick={loadInbox}
          disabled={loading || !emailNorm}
          variant="outline"
          size="sm"
          className="border-white/10 bg-white/5 text-slate-200 hover:bg-white/10 h-10"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      <div data-testid="inbox-message-list" className="h24-card overflow-hidden">
        {loadingList || loading ? (
          <div className="flex items-center justify-center py-16 text-slate-500">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : assignments.length === 0 ? (
          <div className="p-12 text-center">
            <Inbox className="h-10 w-10 text-slate-700 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No connected mailboxes</p>
            <p className="text-slate-600 text-sm mt-1">Connect an Outlook mailbox in the Mailboxes tab first.</p>
          </div>
        ) : !messages || messages.length === 0 ? (
          <div className="p-12 text-center">
            <MailOpen className="h-10 w-10 text-slate-700 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No messages</p>
            <p className="text-slate-600 text-sm mt-1">This mailbox's inbox is empty, or nothing recent to show.</p>
          </div>
        ) : (
          <ul className="divide-y divide-white/5">
            {messages.map((m) => (
              <li key={m.id} className="px-5 py-4 hover:bg-white/[0.025] transition-colors">
                <div className="flex items-start gap-3">
                  <div className="h-8 w-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center shrink-0 mt-0.5">
                    <Mail className={`h-4 w-4 ${m.is_read ? "text-slate-600" : "text-sky-400"}`} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <div className={`truncate ${m.is_read ? "text-slate-300" : "text-slate-100 font-semibold"}`}>
                        {m.subject || "(no subject)"}
                      </div>
                      <div className="text-xs text-slate-500 shrink-0">{timeAgo(m.received)}</div>
                    </div>
                    <div className="text-xs text-slate-500 truncate mt-0.5">{m.from}</div>
                    {m.preview && (
                      <p className="text-xs text-slate-500 mt-1 line-clamp-2">{m.preview}</p>
                    )}
                    {m.web_link && (
                      <a
                        href={m.web_link}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-sky-400 hover:text-sky-300 mt-1.5"
                      >
                        Open in Outlook <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
