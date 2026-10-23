/**
 * Detect desktop mode.
 * Tauri v2 injects __TAURI_INTERNALS__ on the window object.
 */
export function isDesktop(): boolean {
  return (
    typeof window !== "undefined" &&
    Boolean((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__)
  );
}
