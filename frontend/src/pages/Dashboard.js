import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import MailboxesTab from "@/components/MailboxesTab";
import AssignmentsTab from "@/components/AssignmentsTab";
import CodeSearchTab from "@/components/CodeSearchTab";

const ERROR_MESSAGES = {
  missing_state: "OAuth failed: missing state.",
  invalid_state: "OAuth session expired or invalid. Please try connecting again.",
  token_exchange_failed: "Microsoft rejected the sign-in. Please retry.",
  no_refresh_token: "No refresh token returned. Check offline_access scope.",
};

export default function Dashboard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isStaff = isAdmin || user?.role === "sub_admin";
  const [active, setActive] = useState(isAdmin ? "mailboxes" : isStaff ? "assignments" : "search");
  const [status, setStatus] = useState({ microsoft_configured: false, gmail_configured: false });
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();

  const loadStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/config/status");
      setStatus(data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    const connected = searchParams.get("connected");
    const error = searchParams.get("error");
    if (connected) {
      toast.success(`Outlook mailbox connected for ${connected}`);
      setActive("mailboxes");
      setRefreshKey((k) => k + 1);
      searchParams.delete("connected");
      setSearchParams(searchParams, { replace: true });
    } else if (error) {
      toast.error(ERROR_MESSAGES[error] || `OAuth error: ${error}`);
      searchParams.delete("error");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-bg grain min-h-screen">
      <Navbar active={active} onChange={setActive} msConfigured={status.microsoft_configured} />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {active === "mailboxes" && (
          <MailboxesTab status={status} refreshKey={refreshKey} onChanged={() => setRefreshKey((k) => k + 1)} />
        )}
        {active === "assignments" && <AssignmentsTab onChanged={() => setRefreshKey((k) => k + 1)} />}
        {active === "search" && <CodeSearchTab />}
      </main>
    </div>
  );
}
