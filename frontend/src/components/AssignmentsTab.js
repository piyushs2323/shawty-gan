import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Loader2, ListChecks, ShieldCheck, Users2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

function ProviderBadge({ provider }) {
  if (provider === "outlook_graph") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20">
        Outlook · Graph
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
      Gmail · IMAP
    </span>
  );
}

function TeamPanel() {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/users/all");
      setMembers(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setRole = async (id, role) => {
    try {
      await api.patch(`/users/${id}/role`, { role });
      toast.success(role === "sub_admin" ? "Promoted to sub-admin" : "Set back to member");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (loading) {
    return (
      <div className="h24-card flex items-center justify-center py-10 text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (members.length === 0) return null;

  return (
    <div className="h24-card overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-white/10 text-slate-300">
        <div className="h-6 w-6 rounded-md bg-white/10 flex items-center justify-center">
          <Users2 className="h-3.5 w-3.5" />
        </div>
        <span className="eyebrow">Team &amp; roles</span>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {members.map((m) => (
            <tr key={m.id} className="border-b border-white/5 last:border-b-0 hover:bg-white/[0.025] transition-colors">
              <td className="px-5 py-3">
                <div className="text-slate-200 font-medium">{m.name || m.email}</div>
                <div className="text-xs text-slate-500">{m.email}</div>
              </td>
              <td className="px-5 py-3">
                {m.role === "sub_admin" ? (
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                    <ShieldCheck className="h-3.5 w-3.5" /> Sub-admin
                  </span>
                ) : (
                  <span className="text-xs text-slate-500">Member</span>
                )}
              </td>
              <td className="px-5 py-3 text-right">
                {m.role === "sub_admin" ? (
                  <Button
                    onClick={() => setRole(m.id, "member")}
                    variant="ghost"
                    size="sm"
                    className="text-slate-400 hover:text-white hover:bg-white/5"
                  >
                    Revoke sub-admin
                  </Button>
                ) : (
                  <Button
                    onClick={() => setRole(m.id, "sub_admin")}
                    variant="outline"
                    size="sm"
                    className="border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                  >
                    Make sub-admin
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AssignmentsTab({ onChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [rows, setRows] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [provider, setProvider] = useState("outlook_graph");
  const [label, setLabel] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [assignmentsRes, usersRes] = await Promise.all([
        api.get("/assignments"),
        api.get("/users"),
      ]);
      setRows(assignmentsRes.data);
      setUsers(usersRes.data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async (e) => {
    e.preventDefault();
    setAdding(true);
    try {
      await api.post("/assignments", { email, provider, label });
      toast.success("Assignment added");
      setEmail("");
      setLabel("");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setAdding(false);
    }
  };

  const changeProvider = async (id, newProvider) => {
    try {
      await api.patch(`/assignments/${id}`, { provider: newProvider });
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const assignToUser = async (id, userId) => {
    try {
      await api.patch(`/assignments/${id}/assign`, { user_id: userId || null });
      toast.success(userId ? "Email assigned" : "Email unassigned");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/assignments/${id}`);
      toast.success("Assignment removed");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="fade-up space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <span className="eyebrow">Access control</span>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-gradient mt-1">
            Email Assignments
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-xl leading-relaxed">
            Map each Netflix recipient address to its provider. Outlook addresses fetch via Microsoft Graph; Gmail
            addresses use the existing catch-all IMAP path.
          </p>
        </div>
        <div className="meter-card px-4 py-3 text-center shrink-0">
          <div className="font-mono-code text-2xl text-white">{rows.length}</div>
          <div className="text-[11px] text-slate-500 uppercase tracking-wide">Mapped addresses</div>
          <div className="meter-fill bg-gradient-to-r from-transparent via-[#E50914] to-transparent" />
        </div>
      </div>

      {isAdmin && (
        <form onSubmit={add} className="h24-card p-5">
          <div className="flex items-center gap-2 mb-4 text-slate-300">
            <div className="h-6 w-6 rounded-md bg-[#E50914]/15 border border-[#E50914]/30 flex items-center justify-center">
              <Plus className="h-3.5 w-3.5 text-[#E50914]" />
            </div>
            <span className="eyebrow">New assignment</span>
          </div>
          <div className="flex flex-col md:flex-row gap-3 md:items-end">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs text-slate-500 uppercase tracking-wide">Netflix email</label>
              <Input
                data-testid="assignment-email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@outlook.com"
                className="bg-black/40 border-white/10 text-slate-100 h-10 focus-visible:ring-[#E50914]/40 focus-visible:border-[#E50914]/50"
              />
            </div>
            <div className="w-full md:w-44 space-y-1.5">
              <label className="text-xs text-slate-500 uppercase tracking-wide">Provider</label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger data-testid="assignment-provider-select" className="bg-black/40 border-white/10 text-slate-100 h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="outlook_graph">Outlook (Graph)</SelectItem>
                  <SelectItem value="gmail_imap">Gmail (IMAP)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="w-full md:w-40 space-y-1.5">
              <label className="text-xs text-slate-500 uppercase tracking-wide">Label (opt)</label>
              <Input
                data-testid="assignment-label-input"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Family plan"
                className="bg-black/40 border-white/10 text-slate-100 h-10 focus-visible:ring-[#E50914]/40 focus-visible:border-[#E50914]/50"
              />
            </div>
            <Button
              type="submit"
              data-testid="add-assignment-button"
              disabled={adding}
              className="bg-[#E50914] hover:bg-[#c40810] text-white font-semibold h-10 shadow-[0_0_20px_-4px_rgba(229,9,20,0.6)] transition-shadow hover:shadow-[0_0_28px_-4px_rgba(229,9,20,0.8)]"
            >
              {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
              Add
            </Button>
          </div>
        </form>
      )}

      <div data-testid="email-assignments-table" className="h24-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-slate-500">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-12 text-center">
            <ListChecks className="h-10 w-10 text-slate-700 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No assignments yet</p>
            <p className="text-slate-600 text-sm mt-1">
              {isAdmin
                ? "Add a Netflix recipient address above to start routing codes."
                : "Nothing has been assigned to you yet — ask an admin to assign a mailbox."}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 text-xs uppercase tracking-wide border-b border-white/10">
                <th className="px-5 py-3 font-medium">Email</th>
                <th className="px-5 py-3 font-medium">Provider</th>
                <th className="px-5 py-3 font-medium">Assigned to</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="group border-b border-white/5 hover:bg-white/[0.025] transition-colors">
                  <td className="px-5 py-3.5 text-slate-200 border-l-2 border-l-transparent group-hover:border-l-[#E50914]/60 transition-colors">
                    <div className="font-medium">{r.email_norm}</div>
                    {r.label && <div className="text-xs text-slate-500">{r.label}</div>}
                  </td>
                  <td className="px-5 py-3.5">
                    {isAdmin ? (
                      <Select value={r.provider} onValueChange={(v) => changeProvider(r.id, v)}>
                        <SelectTrigger className="h-8 w-40 bg-black/30 border-white/10 text-xs text-slate-200">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="outlook_graph">Outlook (Graph)</SelectItem>
                          <SelectItem value="gmail_imap">Gmail (IMAP)</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <ProviderBadge provider={r.provider} />
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <Select
                      value={r.assigned_user_id || "unassigned"}
                      onValueChange={(v) => assignToUser(r.id, v === "unassigned" ? null : v)}
                    >
                      <SelectTrigger
                        data-testid={`assign-user-select-${r.email_norm}`}
                        className="h-8 w-44 bg-black/30 border-white/10 text-xs text-slate-200"
                      >
                        <SelectValue placeholder="Unassigned" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unassigned">Unassigned</SelectItem>
                        {users.map((u) => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.name || u.email}
                            {u.role === "sub_admin" && <span className="text-emerald-400"> · Sub-admin</span>}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-5 py-3.5">
                    {r.provider === "outlook_graph" ? (
                      r.mailbox_status === "connected" ? (
                        <span className="inline-flex items-center gap-2 text-emerald-400 text-xs font-medium">
                          <span className="live-dot" /> Connected
                        </span>
                      ) : r.mailbox_status === "needs_reconnect" ? (
                        <span className="inline-flex items-center gap-2 text-rose-400 text-xs font-medium">
                          <span className="live-dot" /> Needs reconnect
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2 text-slate-500 text-xs">
                          <span className="h-[7px] w-[7px] rounded-full border border-slate-600" /> Not connected
                        </span>
                      )
                    ) : (
                      <ProviderBadge provider={r.provider} />
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {isAdmin && (
                      <Button
                        data-testid={`delete-assignment-${r.email_norm}`}
                        onClick={() => remove(r.id)}
                        variant="ghost"
                        size="sm"
                        className="text-slate-500 hover:text-rose-400 hover:bg-rose-500/10"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {isAdmin && <TeamPanel />}
    </div>
  );
}
