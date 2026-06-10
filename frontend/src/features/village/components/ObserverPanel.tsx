import type { GameScreenModel } from "../../../gameClient/uiTypes";

interface ObserverPanelProps {
  screen: GameScreenModel;
}

export function ObserverPanel({ screen }: ObserverPanelProps) {
  return (
    <div className="wa-observer-panel">
      <p className="wa-kicker">観戦</p>
      <h2>{screen.observerRecord?.title ?? "語り部の記録"}</h2>
      <p>終わった村や観戦用の記録では、答え合わせを読み返せます。</p>
      <div className="wa-observer-lines">
        {(screen.observerRecord?.lines ?? ["この村ではまだ記録が開かれていません"]).map(
          (line) => (
            <span key={line}>{line}</span>
          ),
        )}
      </div>
    </div>
  );
}
