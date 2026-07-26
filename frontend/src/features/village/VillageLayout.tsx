import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import type { GameSetupOptionsResponse } from "../../gameClient/wireTypes";
import type { PublicRuntimeConfig } from "../../gameClient/GameClient";
import type {
  GameScreenModel,
  PublicGameSummary,
  SetupDraft,
  TurnActionSubmit,
  ViewId,
} from "../../gameClient/uiTypes";
import type { AuthState } from "../../data/AuthClient";
import { dawnTableSkin } from "../../skins/dawnTableSkin";
import { useUiStore } from "../../store/uiStore";
import { ObserverPanel } from "./components/ObserverPanel";
import { AuthPanel } from "./components/AuthPanel";
import { RecordsPanel } from "./components/RecordsPanel";
import { RoundTable } from "./components/RoundTable";
import { TurnPanel } from "./components/TurnPanel";
import { VillageNav } from "./components/VillageNav";
import { VillageSetup } from "./components/VillageSetup";
import { VillageTimeline } from "./components/VillageTimeline";

interface VillageLayoutProps {
  activeView: ViewId;
  auth: AuthState;
  games: PublicGameSummary[];
  isCreatingGame: boolean;
  isSubmittingAction: boolean;
  isUpdatingAuth: boolean;
  errorMessage: string | null;
  onCreateGame: (draft: SetupDraft) => void;
  onResumeGame: (gameId: string) => void;
  onRecover: () => void;
  onSignIn: (email: string, password: string) => void;
  onSignOut: () => void;
  onSubmitAction: (action: TurnActionSubmit) => void;
  screen: GameScreenModel;
  setupOptions: GameSetupOptionsResponse;
  runtimeConfig: PublicRuntimeConfig;
}

export function VillageLayout({
  activeView,
  auth,
  games,
  isCreatingGame,
  isSubmittingAction,
  isUpdatingAuth,
  errorMessage,
  onCreateGame,
  onResumeGame,
  onRecover,
  onSignIn,
  onSignOut,
  onSubmitAction,
  screen,
  setupOptions,
  runtimeConfig,
}: VillageLayoutProps) {
  const setActiveView = useUiStore((state) => state.setActiveView);
  const desktopBreakpoint = runtimeConfig.ui.desktop_breakpoint;
  const compactLayout = useCompactLayout(desktopBreakpoint);
  const runtimeStyle = {
    "--wa-space": `${runtimeConfig.ui.spacing_unit}px`,
    "--wa-desktop-breakpoint": `${desktopBreakpoint}px`,
  } as CSSProperties;

  return (
    <div
      className="wa-app"
      data-compact-layout={compactLayout}
      data-config-revision={runtimeConfig.config_revision}
      data-contract-version={runtimeConfig.contract_version}
      data-game-version={screen.version}
      data-message-max-chars={runtimeConfig.limits.message_max_chars}
      data-motion={runtimeConfig.ui.motion}
      data-operation-status={
        errorMessage ? "failed" : isCreatingGame || isSubmittingAction ? "running" : "succeeded"
      }
      data-skin={dawnTableSkin.id}
      data-story-theme-id={screen.storyThemeId ?? "setup"}
      data-theme-id={runtimeConfig.ui.theme_id}
      data-view-mode={activeView}
      style={runtimeStyle}
    >
      <VillageNav
        activeView={activeView}
        storyPremise={screen.tableSubtitle}
        storyTitle={screen.tableTitle}
        onNavigate={setActiveView}
      />
      <main className="wa-main-shell">
        <AuthPanel
          auth={auth}
          isPending={isUpdatingAuth}
          onSignIn={onSignIn}
          onSignOut={onSignOut}
        />
        {errorMessage ? (
          <section className="wa-error-banner" role="alert">
            <div>
              <strong>操作を完了できませんでした</strong>
              <p>{errorMessage}</p>
            </div>
            <button type="button" onClick={onRecover}>
              最新状態を読み込む
            </button>
          </section>
        ) : null}
        <section className="wa-hero-status" aria-label="ゲームの状態">
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
            uiSettings={runtimeConfig.ui}
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
                  messageMaxChars={runtimeConfig.limits.message_max_chars}
                  onSubmit={onSubmitAction}
                  panel={screen.turnPanel}
                />
              )}
            </aside>

            <section className="wa-story-zone" aria-label="ゲームの記録">
              <VillageTimeline entries={screen.timeline} />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function useCompactLayout(breakpoint: number): boolean {
  const [compact, setCompact] = useState(() => window.innerWidth <= breakpoint);

  useEffect(() => {
    const update = () => setCompact(window.innerWidth <= breakpoint);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [breakpoint]);

  return compact;
}
