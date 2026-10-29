import { createContext, useCallback, useContext, type ReactNode } from "react";

/**
 * The signed-in person's Lead Gen permissions, as the Staff Portal's access
 * registry reported them through /api/auth/me (e.g. "leads.save",
 * "outreach.send_bulk"). Only used to hide what they can't do: every backend
 * route checks the permission again, so hiding a button is never the
 * security boundary.
 */
const PermissionsContext = createContext<readonly string[]>([]);

export function PermissionsProvider({ permissions, children }: { permissions: readonly string[]; children: ReactNode }) {
  return <PermissionsContext.Provider value={permissions}>{children}</PermissionsContext.Provider>;
}

/** `const can = useCan(); can("leads.export")` */
export function useCan(): (permission: string) => boolean {
  const permissions = useContext(PermissionsContext);
  return useCallback((permission: string) => permissions.includes(permission), [permissions]);
}
