import { API_BASE_URL } from "@/src/apiConfig";

/** Lead Matchmaker API calls. Same session cookie as the rest of Lead Gen (credentials: "include"). */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body: any, status: number): string {
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(-1)[0] ?? "field"}: ${x.msg}`).join("; ");
  if (status === 401) return "Your session has expired. Sign in again through the Staff Portal.";
  if (status === 403) return "You don't have permission to do this.";
  if (status >= 500) return "The server had a problem. Try again shortly.";
  return `Request failed (${status})`;
}

export async function mm<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/matchmaker${path}`, {
      credentials: "include",
      ...rest,
      headers: json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, res.status));
  return body as T;
}

/** Download a file from an authenticated endpoint. */
export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/matchmaker${path}`, { credentials: "include" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detailMessage(body, res.status));
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function upload<T = any>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return mm<T>(path, { method: "POST", body: form });
}

export function formatDate(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
