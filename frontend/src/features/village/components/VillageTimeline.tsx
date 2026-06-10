import type { TimelineEntry } from "../../../gameClient/uiTypes";

interface VillageTimelineProps {
  compact?: boolean;
  entries: TimelineEntry[];
}

export function VillageTimeline({ compact = false, entries }: VillageTimelineProps) {
  const visibleEntries = compact ? entries.slice(-4) : entries;
  return (
    <div className={compact ? "wa-timeline wa-timeline-compact" : "wa-timeline"}>
      <div className="wa-section-heading">
        <p className="wa-kicker">村の記録</p>
        <h2>{compact ? "直近の出来事" : "公開された出来事"}</h2>
      </div>
      <ol>
        {visibleEntries.map((entry) => (
          <li className={`wa-timeline-entry wa-timeline-${entry.tone}`} key={entry.sequence}>
            <span>{entry.dayLabel}</span>
            <div>
              <strong>{entry.label}</strong>
              <p>{entry.detail}</p>
              <small>{entry.actorName}</small>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
