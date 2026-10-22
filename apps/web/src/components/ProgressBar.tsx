import { formatPercentage } from "../utils/format.js";

interface ProgressBarProps {
  positionMs?: number | null;
  durationMs?: number | null;
  showLabel?: boolean;
  className?: string;
}

export function ProgressBar({
  positionMs = 0,
  durationMs = 0,
  showLabel = false,
  className = "",
}: ProgressBarProps) {
  const percent = formatPercentage(positionMs ?? 0, durationMs ?? 0);

  return (
    <div className={`progress-container ${className}`}>
      <div className="progress-track" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <div
          className="progress-fill"
          style={{ width: `${percent}%` }}
        />
      </div>
      {showLabel && percent > 0 && (
        <span className="progress-label">{percent}%</span>
      )}
    </div>
  );
}
