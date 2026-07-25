import type { PublicGameSummary } from "../../../gameClient/uiTypes";

interface RecordsPanelProps {
  games: PublicGameSummary[];
  onResumeGame: (gameId: string) => void;
}

export function RecordsPanel({ games, onResumeGame }: RecordsPanelProps) {
  return (
    <div className="wa-records">
      <p className="wa-kicker">記録</p>
      <h2>語り部の本棚</h2>
      <div className="wa-record-list">
        {games.map((game, index) => (
          <article className="wa-record-row" key={game.game_id}>
            <span>村 {index + 1}</span>
            <strong>{game.status === "completed" ? "終わった村" : "進行中の村"}</strong>
            <p>
              {game.day}日目 / 生存 {game.alive_count}人 /{" "}
              {game.winner === "villagers"
                ? "村人陣営の勝利"
                : game.winner === "werewolves"
                  ? "人狼陣営の勝利"
                : "勝負中"}
            </p>
            <button
              className="wa-record-resume"
              onClick={() => onResumeGame(game.game_id)}
              type="button"
            >
              {game.status === "running" ? "続きから" : "結果を見る"}
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}
