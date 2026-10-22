import type { LectureStatus } from "@lecture-platform/shared";
import { useTranslation } from "../i18n/index.js";
import type { TranslationKey } from "../i18n/en.js";

interface StatusBadgeProps {
  status: LectureStatus;
  published?: boolean;
}

export function StatusBadge({ status, published = true }: StatusBadgeProps) {
  const { t } = useTranslation();

  if (!published) {
    return (
      <span className="badge badge-draft">
        {t("lectures.unpublished")}
      </span>
    );
  }

  const styles: Record<LectureStatus, { className: string; labelKey: TranslationKey }> = {
    ready: { className: "badge badge-ready", labelKey: "lectures.status.ready" },
    processing: { className: "badge badge-processing", labelKey: "lectures.status.processing" },
    failed: { className: "badge badge-failed", labelKey: "lectures.status.failed" },
    uploaded: { className: "badge badge-processing", labelKey: "lectures.status.processing" },
  };

  const current = styles[status] ?? styles.uploaded;

  return (
    <span className={current.className}>
      {t(current.labelKey)}
    </span>
  );
}
