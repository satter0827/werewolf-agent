import type { GameScreenModel } from "../../../gameClient/uiTypes";

interface ObserverPanelProps {
  isSubmitting: boolean;
  onAdvance: () => void;
  screen: GameScreenModel;
}

export function ObserverPanel({ isSubmitting, onAdvance, screen }: ObserverPanelProps) {
  return (
    <div className="wa-observer-panel">
      <p className="wa-kicker">観戦</p>
      <h2>{screen.observerRecord?.title ?? "公開された記録"}</h2>
      <p>公開された発言と出来事を、時系列で読み返せます。</p>
      <div className="wa-observer-lines">
        {(screen.observerRecord?.entries.length
          ? screen.observerRecord.entries
          : [{ sequence: 0, text: "まだ公開された記録がありません" }]
        ).map((entry) => (
          <span key={entry.sequence}>{entry.text}</span>
        ))}
      </div>
      {screen.status === "running" ? (
        <button
          className="wa-primary-action"
          disabled={isSubmitting}
          onClick={onAdvance}
          type="button"
        >
          {isSubmitting ? "進行中" : "進める"}
        </button>
      ) : null}
    </div>
  );
}
