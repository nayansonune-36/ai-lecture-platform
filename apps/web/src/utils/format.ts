/**
 * Media position and duration formatting helpers.
 * Media positions are integer milliseconds in DB/API and formatted to MM:SS or H:MM:SS in the UI.
 */

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || isNaN(ms) || ms < 0) {
    return "00:00";
  }

  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const pad = (n: number) => n.toString().padStart(2, "0");

  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

export function formatPercentage(part: number, total: number): number {
  if (!total || total <= 0 || !part || part <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((part / total) * 100)));
}
