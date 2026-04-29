/**
 * PM-mode role detection.
 *
 * Per spec §4.13 PM mode is a localStorage toggle (`tripwire-role`
 * key set to `pm`) with a `?role=pm` URL flag for dev convenience.
 * Mirrors the backend's `X-Tripwire-Role: pm` header contract in
 * `src/tripwire/ui/services/role_gate.py`.
 *
 * No security boundary — semantic separation only. Server is the
 * source of truth for redaction; the UI flag is belt-and-braces.
 */

export const PM_ROLE_LOCAL_STORAGE_KEY = "tripwire-role";
export const PM_ROLE_HEADER = "X-Tripwire-Role";
export const PM_ROLE_VALUE = "pm";

/** Returns true when the current viewer is in PM mode. Reads
 *  `roleParam` first (typically from URL `?role=`) then falls
 *  back to localStorage. */
export function isPmMode(roleParam?: string | null): boolean {
  if (roleParam === PM_ROLE_VALUE) return true;
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(PM_ROLE_LOCAL_STORAGE_KEY) === PM_ROLE_VALUE;
  } catch {
    return false;
  }
}

/** Header dict to merge into a fetch options bag. Empty object when
 *  not in PM mode so the caller can spread unconditionally. */
export function pmRoleHeaders(pmMode: boolean): Record<string, string> {
  return pmMode ? { [PM_ROLE_HEADER]: PM_ROLE_VALUE } : {};
}
