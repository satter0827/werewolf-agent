import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { browserConfigError } from "./config";
import { gameClient } from "./data/ApiGameClient";
import { authClient } from "./data/AuthClient";
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
  const startupConfigError = browserConfigError();
  const queriesEnabled = startupConfigError === null;
  const privatePlayerId = activeView === "play" ? manualPlayerId : "";

  const setupQuery = useQuery({
    enabled: queriesEnabled,
    queryKey: ["setup-options"],
    queryFn: () => gameClient.getSetupOptions(),
  });
  const authQuery = useQuery({
    enabled: queriesEnabled,
    queryKey: ["auth"],
    queryFn: () => authClient.current(),
  });
  const runtimeConfigQuery = useQuery({
    enabled: queriesEnabled,
    queryKey: ["runtime-config"],
    queryFn: () => gameClient.getRuntimeConfig(),
  });
  const screenQuery = useQuery({
    enabled: queriesEnabled && activeGameId !== null,
    queryKey: ["game-screen", activeGameId, privatePlayerId],
    queryFn: () => gameClient.getScreen(activeGameId, privatePlayerId),
  });
  const gamesQuery = useQuery({
    enabled: queriesEnabled,
    queryKey: ["game-list"],
    queryFn: () => gameClient.listGames(),
  });
  const setupOptions = setupQuery.data;
  const runtimeConfig = runtimeConfigQuery.data;
  const gameList = gamesQuery.data;

  useEffect(() => {
    const configured = runtimeConfig?.ui.default_manual_player_id;
    if (!manualPlayerId && typeof configured === "string" && configured) {
      setManualPlayerId(configured);
    }
  }, [manualPlayerId, runtimeConfig, setManualPlayerId]);

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
      setActiveView(draft.manualPlayerId ? "play" : "observe");
      void queryClient.invalidateQueries({ queryKey: ["game-screen"] });
      void queryClient.invalidateQueries({ queryKey: ["game-list"] });
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
    },
  });
  const signInMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authClient.signIn(email, password),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
  });
  const signOutMutation = useMutation({
    mutationFn: () => authClient.signOut(),
    onSuccess: async () => {
      setActiveGameId(null);
      setActiveView("setup");
      await queryClient.invalidateQueries();
    },
  });

  if (startupConfigError) {
    return <div className="wa-loading" role="alert">{startupConfigError.message}</div>;
  }

  if (
    setupQuery.isLoading ||
    authQuery.isLoading ||
    runtimeConfigQuery.isLoading ||
    (activeGameId !== null && screenQuery.isLoading) ||
    gamesQuery.isLoading
  ) {
    return <div className="wa-loading">村の夜明けを準備しています</div>;
  }

  if (
    setupQuery.isError ||
    authQuery.isError ||
    runtimeConfigQuery.isError ||
    (activeGameId !== null && screenQuery.isError) ||
    gamesQuery.isError ||
    !setupOptions ||
    !authQuery.data ||
    !runtimeConfig ||
    !gameList
  ) {
    return (
      <div className="wa-loading" role="alert">
        <p>村の準備に失敗しました。</p>
        <button type="button" onClick={() => void queryClient.invalidateQueries()}>
          もう一度読み込む
        </button>
      </div>
    );
  }
  const screenSource = screenQuery.data ?? setupPreviewScreen(setupOptions);

  const screen = mapGameScreen({ screen: screenSource, manualPlayerId });

  return (
    <VillageLayout
      activeView={activeView}
      auth={authQuery.data}
      games={gameList.games}
      isCreatingGame={createGameMutation.isPending}
      isSubmittingAction={submitActionMutation.isPending}
      isUpdatingAuth={signInMutation.isPending || signOutMutation.isPending}
      errorMessage={mutationError(
        createGameMutation.error,
        submitActionMutation.error,
        signInMutation.error,
        signOutMutation.error,
      )}
      onCreateGame={(draft) => createGameMutation.mutate(draft)}
      onResumeGame={(gameId) => {
        setActiveGameId(gameId);
        const game = gameList.games.find((item) => item.game_id === gameId);
        setActiveView(game?.status === "completed" ? "observe" : "play");
      }}
      onSignIn={(email, password) => signInMutation.mutate({ email, password })}
      onSignOut={() => signOutMutation.mutate()}
      onRecover={() => {
        createGameMutation.reset();
        submitActionMutation.reset();
        signInMutation.reset();
        signOutMutation.reset();
        void queryClient.invalidateQueries();
      }}
      onSubmitAction={(action) => submitActionMutation.mutate(action)}
      screen={screen}
      setupOptions={setupOptions}
      runtimeConfig={runtimeConfig}
    />
  );
}

function mutationError(...errors: Array<Error | null>): string | null {
  return errors.find((error) => error !== null)?.message ?? null;
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
    manual_player_id: draft.manualPlayerId || null,
    rules: setupOptions.default_rules,
  };
}
