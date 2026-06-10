import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { gameClient } from "./data/SupabaseGameClient";
import { VillageLayout } from "./features/village/VillageLayout";
import { mapGameScreen } from "./gameClient/screenAdapter";
import { setupPreviewScreen } from "./gameClient/setupOptions";
import type { SetupDraft, TurnActionSubmit } from "./gameClient/uiTypes";
import type { CreateGameRequest, GameSetupOptionsResponse } from "./gameClient/wireTypes";
import { useUiStore } from "./store/uiStore";

export function App() {
  const queryClient = useQueryClient();
  const activeView = useUiStore((state) => state.activeView);
  const activeGameId = useUiStore((state) => state.activeGameId);
  const manualPlayerId = useUiStore((state) => state.manualPlayerId);
  const setActiveGameId = useUiStore((state) => state.setActiveGameId);
  const setActiveView = useUiStore((state) => state.setActiveView);
  const setManualPlayerId = useUiStore((state) => state.setManualPlayerId);

  const setupQuery = useQuery({
    queryKey: ["setup-options"],
    queryFn: () => gameClient.getSetupOptions(),
  });
  const screenQuery = useQuery({
    enabled: activeGameId !== null,
    queryKey: ["game-screen", activeGameId, manualPlayerId],
    queryFn: () => gameClient.getScreen(activeGameId, manualPlayerId),
  });
  const revealQuery = useQuery({
    enabled: activeView === "observe" && activeGameId !== null,
    queryKey: ["game-reveal", activeGameId],
    queryFn: () => gameClient.getReveal(activeGameId ?? ""),
  });
  const gamesQuery = useQuery({
    queryKey: ["game-list"],
    queryFn: () => gameClient.listGames(),
  });
  const setupOptions = setupQuery.data;
  const gameList = gamesQuery.data;

  const createGameMutation = useMutation({
    mutationFn: (draft: SetupDraft) => {
      if (!setupOptions) {
        throw new Error("setup options are not loaded");
      }
      return gameClient.createGame(createGameRequest(draft, setupOptions));
    },
    onSuccess: (response, draft) => {
      setActiveGameId(response.game_id);
      setManualPlayerId(draft.manualPlayerId);
      setActiveView("play");
      void queryClient.invalidateQueries({ queryKey: ["game-screen"] });
      void queryClient.invalidateQueries({ queryKey: ["game-list"] });
      void queryClient.invalidateQueries({ queryKey: ["game-reveal"] });
    },
  });
  const submitActionMutation = useMutation({
    mutationFn: async (action: TurnActionSubmit) => {
      if (activeGameId === null) {
        throw new Error("game is not selected");
      }
      if (action.type === "advance") {
        await gameClient.advance({ gameId: activeGameId });
        return;
      }
      await gameClient.submitAction({
        gameId: activeGameId,
        playerId: manualPlayerId,
        action: {
          type: action.type,
          message: action.message,
          target_id: action.targetId,
        },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["game-screen"] });
      void queryClient.invalidateQueries({ queryKey: ["game-list"] });
      void queryClient.invalidateQueries({ queryKey: ["game-reveal"] });
    },
  });

  if (setupQuery.isLoading || (activeGameId !== null && screenQuery.isLoading) || gamesQuery.isLoading) {
    return <div className="wa-loading">村の夜明けを準備しています</div>;
  }

  if (
    setupQuery.isError ||
    (activeGameId !== null && screenQuery.isError) ||
    gamesQuery.isError ||
    !setupOptions ||
    !gameList
  ) {
    return <div className="wa-loading">村の準備に失敗しました</div>;
  }
  const screenSource = screenQuery.data ?? setupPreviewScreen(setupOptions);

  const screen = mapGameScreen({
    screen: {
      ...screenSource,
      reveal: activeView === "observe" ? revealQuery.data ?? null : null,
    },
    manualPlayerId,
  });

  return (
    <VillageLayout
      activeView={activeView}
      games={gameList.games}
      isCreatingGame={createGameMutation.isPending}
      isSubmittingAction={submitActionMutation.isPending}
      onCreateGame={(draft) => createGameMutation.mutate(draft)}
      onResumeGame={(gameId) => {
        setActiveGameId(gameId);
        setActiveView("play");
      }}
      onSubmitAction={(action) => submitActionMutation.mutate(action)}
      screen={screen}
      setupOptions={setupOptions}
    />
  );
}

function createGameRequest(
  draft: SetupDraft,
  setupOptions: GameSetupOptionsResponse,
): CreateGameRequest {
  const selectedPreset = setupOptions.setup_presets.find(
    (preset) => preset.id === draft.setupPresetId,
  );
  return {
    seed: draft.seed.trim() ? Number(draft.seed) : null,
    scenario_id: draft.scenarioId,
    setup_preset_id: draft.setupPresetId,
    role_counts: selectedPreset?.role_counts ?? setupOptions.default_role_counts,
    manual_player_id: draft.manualPlayerId,
    rules: setupOptions.default_rules,
  };
}
