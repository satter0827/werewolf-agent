import type { GameScreenModel } from "../../../gameClient/uiTypes";

interface ObserverPanelProps {
  screen: GameScreenModel;
}

export function ObserverPanel({ screen }: ObserverPanelProps) {
  return (
    <div className="wa-observer-panel">
      <p className="wa-kicker">観戦</p>
      <h2>{screen.observerRecord?.title ?? "公開された記録"}</h2>
      <p>村で公開された発言と出来事を、時系列で読み返せます。</p>
      <div className="wa-observer-lines">
        {(screen.observerRecord?.lines.length
          ? screen.observerRecord.lines
          : ["この村ではまだ公開された記録がありません"]
        ).map(
          (line) => (
            <span key={line}>{line}</span>
          ),
        )}
      </div>
    </div>
  );
}
