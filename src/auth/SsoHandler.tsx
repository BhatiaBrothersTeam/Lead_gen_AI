import { useEffect, useState } from "react";
import { Loader2, ShieldAlert } from "lucide-react";
import { API_BASE_URL } from "@/src/apiConfig";

const PORTAL_URL = process.env.PORTAL_URL || "http://localhost:3000";

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

    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/auth/sso`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ token }),
        });

        if (!res.ok) {
          throw new Error("sso_failed");
        }

        // Drop the one-time token from the URL and land on the real app.
        window.location.replace("/");
      } catch {
        setError("Your sign-in link expired or is invalid.");
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
