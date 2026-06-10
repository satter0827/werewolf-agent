import type { GameScreenModel } from "../../../gameClient/uiTypes";

interface RoundTableProps {
  screen: GameScreenModel;
}

export function RoundTable({ screen }: RoundTableProps) {
  return (
    <div className="wa-round-table">
      <div className="wa-table-center">
        <span>{screen.dayLabel}</span>
        <strong>{screen.phaseLabel}</strong>
        <p>{screen.winnerLabel ?? "まだ勝負は続いています"}</p>
      </div>
      {screen.seats.map((seat, index) => (
        <article
          className={`wa-seat wa-seat-${index + 1} wa-seat-${seat.seatTone}`}
          key={seat.id}
        >
          <div className={`wa-portrait ${seat.portraitKey}`} aria-hidden="true" />
          <div className="wa-seat-copy">
            <div>
              <strong>{seat.displayName}</strong>
              {seat.isManual ? <span>あなた</span> : null}
            </div>
            <p>{seat.currentMood}</p>
            <small>{seat.lastPublicLine}</small>
          </div>
        </article>
      ))}
    </div>
  );
}
