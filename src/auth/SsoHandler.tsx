import { useEffect, useState } from "react";
import { Loader2, ShieldAlert } from "lucide-react";
import { API_BASE_URL } from "@/src/apiConfig";

const PORTAL_URL = process.env.PORTAL_URL ;

// The handoff token works exactly once (the backend rejects a reused jti).
// React StrictMode runs effects twice in development, which would send the
// same token twice and fail the second exchange, so only exchange it once.
let exchangeStarted = false;

// Reasons the backend passes through from the Staff Portal's access check
// (backend/api/routes/access.py), plus its own "portal_unavailable".
function noAccessMessage(reason: string): string {
  switch (reason) {
    case "portal_unavailable":
      return "The Staff Portal couldn't confirm your access right now. Please try again.";
    case "unknown_user":
      return "There's no Staff Portal account for you yet.";
    case "account_pending":
      return "Your Staff Portal account is waiting for an administrator's approval.";
    case "account_rejected":
    case "account_suspended":
      return "Your Staff Portal account isn't active.";
    case "application_inactive":
      return "Lead Gen Agent is currently switched off in the Staff Portal.";
    default:
      return "You don't have access to Lead Gen Agent.";
  }
}

/**
 * Step 2+ of the cross-app SSO handoff (see the Staff Portal's
 * src/lib/sso.ts for the full flow, and backend/api/routes/auth.py for the
 * verification side here).
 *
 * This app has no router, so main.tsx renders this component directly
 * whenever the browser lands on /auth/sso?token=... instead of mounting the
 * normal <App />. It exchanges the portal's short-lived handoff token for
 * this app's own session cookie, then hands off to the real app.
 */
export function SsoHandler() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");

    if (!token) {
      window.location.replace(`${PORTAL_URL}/login`);
      return;
    }

    if (exchangeStarted) return;
    exchangeStarted = true;

    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/auth/sso`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ token }),
        });

        if (res.status === 503) {
          throw new Error("not_configured");
        }
        if (res.status === 403) {
          const body = await res.json().catch(() => ({}));
          throw new Error(`no_access:${typeof body?.reason === "string" ? body.reason : ""}`);
        }
        if (!res.ok) {
          throw new Error("sso_failed");
        }

        // Drop the one-time token from the URL and land on the real app,
        // back on the page the person was opening (e.g. a lead link), if any.
        let returnTo = "/";
        try {
          const saved = sessionStorage.getItem("lga_return_to");
          sessionStorage.removeItem("lga_return_to");
          // Same-site paths only: never an absolute or protocol-relative URL.
          if (saved && /^\/[A-Za-z0-9/_-]*$/.test(saved) && !saved.startsWith("//")) returnTo = saved;
        } catch {
          /* storage unavailable */
        }
        window.location.replace(returnTo);
      } catch (err) {
        const reason = err instanceof Error ? err.message : "";
        setError(
          reason === "not_configured"
            ? "Sign-in isn't set up on this server yet. Please contact an administrator."
            : reason.startsWith("no_access:")
              ? noAccessMessage(reason.slice("no_access:".length))
              : "Your sign-in link expired or is invalid.",
        );
        window.setTimeout(() => {
          window.location.replace(`${PORTAL_URL}/login?error=sso_failed`);
        }, 1800);
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-[#FAFAFD] flex items-center justify-center p-6">
      <div className="bg-white border border-[#EDEDF4] shadow-sm rounded-2xl p-8 max-w-sm w-full flex flex-col items-center text-center gap-3">
        {error ? (
          <>
            <div className="w-10 h-10 rounded-full bg-red-50 text-red-500 flex items-center justify-center border border-red-100">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <h1 className="text-[15px] font-bold text-[#111118]">{error}</h1>
            <p className="text-[13px] text-[#7A7A8F]">Taking you back to the Staff Portal…</p>
          </>
        ) : (
          <>
            <Loader2 className="w-6 h-6 text-[#6B2BFF] animate-spin" />
            <h1 className="text-[15px] font-bold text-[#111118]">Signing you in…</h1>
            <p className="text-[13px] text-[#7A7A8F]">Checking your Bhatia Brothers Staff Portal sign-in.</p>
          </>
        )}
      </div>
    </div>
  );
}
