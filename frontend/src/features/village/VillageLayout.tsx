import type { GameSetupOptionsResponse } from "../../gameClient/wireTypes";
import type {
  GameScreenModel,
  PublicGameSummary,
  SetupDraft,
  TurnActionSubmit,
  ViewId,
} from "../../gameClient/uiTypes";
import { dawnTableSkin } from "../../skins/dawnTableSkin";
import { useUiStore } from "../../store/uiStore";
import { ObserverPanel } from "./components/ObserverPanel";
import { RecordsPanel } from "./components/RecordsPanel";
import { RoundTable } from "./components/RoundTable";
import { TurnPanel } from "./components/TurnPanel";
import { VillageNav } from "./components/VillageNav";
import { VillageSetup } from "./components/VillageSetup";
import { VillageTimeline } from "./components/VillageTimeline";

interface VillageLayoutProps {
  activeView: ViewId;
  games: PublicGameSummary[];
  isCreatingGame: boolean;
  isSubmittingAction: boolean;
  onCreateGame: (draft: SetupDraft) => void;
  onResumeGame: (gameId: string) => void;
  onSubmitAction: (action: TurnActionSubmit) => void;
  screen: GameScreenModel;
  setupOptions: GameSetupOptionsResponse;
}

export function VillageLayout({
  activeView,
  games,
  isCreatingGame,
  isSubmittingAction,
  onCreateGame,
  onResumeGame,
  onSubmitAction,
  screen,
  setupOptions,
}: VillageLayoutProps) {
  const setActiveView = useUiStore((state) => state.setActiveView);

  return (
    <div className="wa-app" data-skin={dawnTableSkin.id}>
      <VillageNav activeView={activeView} onNavigate={setActiveView} />
      <main className="wa-main-shell">
        <section className="wa-hero-status" aria-label="村の状態">
          <div>
            <p className="wa-kicker">{dawnTableSkin.name}</p>
            <h1>{screen.tableTitle}</h1>
            <p>{screen.tableSubtitle}</p>
          </div>
          <div className="wa-status-pills">
            <span>{screen.dayLabel}</span>
            <span>{screen.phaseLabel}</span>
            <span>生存 {screen.aliveCount}人</span>
          </div>
        </section>

        {activeView === "setup" ? (
          <VillageSetup
            isCreating={isCreatingGame}
            onCreate={onCreateGame}
            setupOptions={setupOptions}
          />
        ) : (
          <div className="wa-game-grid">
            <section className="wa-table-zone" aria-label="プレイ">
              {activeView === "records" ? (
                <RecordsPanel games={games} onResumeGame={onResumeGame} />
              ) : (
                <RoundTable screen={screen} />
              )}
            </section>

            <aside className="wa-command-zone" aria-label="あなたの手番">
              {activeView === "observe" ? (
                <ObserverPanel screen={screen} />
              ) : activeView === "records" ? (
                <VillageTimeline entries={screen.timeline} compact />
              ) : (
                <TurnPanel
                  isSubmitting={isSubmittingAction}
                  onSubmit={onSubmitAction}
                  panel={screen.turnPanel}
                />
              )}
            </aside>

            <section className="wa-story-zone" aria-label="村の記録">
              <VillageTimeline entries={screen.timeline} />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
