import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { useUiStore } from "./store/uiStore";
import { sampleScreenSource, sampleSetupOptions } from "./test/gameSamples";
import type { GameScreenSource } from "./gameClient/wireTypes";

const gameClientMock = vi.hoisted(() => ({
  advance: vi.fn(),
  createGame: vi.fn(),
  getRuntimeConfig: vi.fn(),
  getScreen: vi.fn(),
  getSetupOptions: vi.fn(),
  listGames: vi.fn(),
  submitAction: vi.fn(),
}));

vi.mock("./data/ApiGameClient", () => ({
  gameClient: gameClientMock,
}));
vi.mock("./data/AuthClient", () => ({
  authClient: {
    current: vi.fn().mockResolvedValue({
      email: null,
      isAnonymous: true,
      isAuthenticated: false,
    }),
    signIn: vi.fn(),
    signOut: vi.fn(),
  },
}));

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App HTTP API flow", () => {
  let currentScreen: GameScreenSource;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("VITE_SUPABASE_URL", "http://127.0.0.1:54321");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "publishable-test");
    vi.stubEnv("VITE_WEREWOLF_API_URL", "http://127.0.0.1:8000");
    currentScreen = sampleScreenSource();
    gameClientMock.getSetupOptions.mockResolvedValue(sampleSetupOptions);
    gameClientMock.getRuntimeConfig.mockResolvedValue({
      contract_version: "v1",
      config_revision: "test",
      setup: sampleSetupOptions,
      limits: {
        game_min_players: 5,
        game_max_players: 8,
        message_max_chars: 120,
        game_list_page_size: 20,
        timeline_page_size: 100,
      },
      features: {
        authentication: true,
        paid_llm_for_members: true,
        admin_reveal: true,
        admin_replay: true,
      },
      ui: {
        desktop_breakpoint: 980,
        spacing_unit: 4,
        theme_id: "dawn-table",
        motion: "system",
        default_manual_player_id: "player-1",
        default_setup_seed: "1",
        operation_poll_interval_ms: 250,
        operation_poll_timeout_ms: 60_000,
      },
    });
    gameClientMock.getScreen.mockImplementation(async () => currentScreen);
    gameClientMock.listGames.mockResolvedValue({ games: [], next_offset: null });
    gameClientMock.advance.mockResolvedValue(currentScreen);
    gameClientMock.createGame.mockImplementation(async (request) => {
      currentScreen = sampleScreenSource();
      currentScreen.state.game_id = "created-game";
      currentScreen.state.scenario_id = request.scenario_id;
      currentScreen.state.scenario_name =
        request.scenario_id === "moon-plaza" ? "月明かりの広場" : "霧の村";
      return {
        game_id: "created-game",
        state: currentScreen.state,
      };
    });
    gameClientMock.submitAction.mockImplementation(async (command) => {
      currentScreen = {
        ...currentScreen,
        state: { ...currentScreen.state, phase: "voting", version: 3 },
        timeline: {
          ...currentScreen.timeline,
          items: [
            ...currentScreen.timeline.items,
            {
              sequence: 3,
              event_sequence: 3,
              version: 3,
              phase: "day_discussion",
              day: 1,
              actor_id: command.playerId,
              event_type: "speech",
              narration: command.action.message,
              payload: { message: command.action.message },
              occurred_at: "2026-06-04T00:01:00Z",
            },
          ],
          next_after: 3,
        },
        observation: {
          game_id: "sample-game",
          player_id: "player-1",
          observation: {
            phase: "voting",
            day: 1,
            me: { id: "player-1", name: "アオイ", role: "seer", status: "alive" },
            known_roles: {},
            available_actions: ["vote"],
            legal_targets: { vote: ["player-2"] },
          },
        },
      };
      return {
        game_id: "sample-game",
        player_id: command.playerId,
        state: currentScreen.state,
        timeline: currentScreen.timeline.items,
      };
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("starts a playable API-backed village from setup choices", async () => {
    useUiStore.setState({
      activeGameId: null,
      activeView: "setup",
      manualPlayerId: "player-1",
    });
    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /月明かりの広場/ }));
    fireEvent.change(screen.getByLabelText("参加方法"), { target: { value: "player-3" } });
    fireEvent.click(screen.getByRole("button", { name: /この村で始める/ }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "月明かりの広場" })).toBeInTheDocument();
    });
    expect(screen.getByText("あなた")).toBeInTheDocument();
    expect(screen.queryByText(/provider|model|token|game_id/i)).not.toBeInTheDocument();
  });

  it("starts an observer-only API-backed village without private observation", async () => {
    useUiStore.setState({
      activeGameId: null,
      activeView: "setup",
      manualPlayerId: "player-1",
    });
    renderApp();

    fireEvent.change(await screen.findByLabelText("参加方法"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "観戦を始める" }));

    await waitFor(() => {
      expect(gameClientMock.createGame).toHaveBeenCalledWith(
        expect.objectContaining({ manual_player_id: null }),
      );
      expect(gameClientMock.getScreen).toHaveBeenCalledWith("created-game", "");
    });
    expect(useUiStore.getState().activeView).toBe("observe");
  });

  it("submits speech and then shows legal vote targets only", async () => {
    useUiStore.setState({
      activeGameId: "sample-game",
      activeView: "play",
      manualPlayerId: "player-1",
    });
    renderApp();

    fireEvent.change(await screen.findByPlaceholderText("村のみんなに伝えること"), {
      target: { value: "今日はレンの投票理由を聞きたいです。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "決定する" }));

    await waitFor(() => {
      expect(screen.getAllByText("投票の時間").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("今日はレンの投票理由を聞きたいです。").length).toBeGreaterThan(0);

    const targetSelect = screen.getByLabelText("相手を選ぶ") as HTMLSelectElement;
    const optionLabels = [...targetSelect.options].map((option) => option.textContent);
    expect(optionLabels).toContain("レン");
    expect(optionLabels).not.toContain("アオイ");
  });

  it("applies the public message length limit to the action form", async () => {
    useUiStore.setState({
      activeGameId: "sample-game",
      activeView: "play",
      manualPlayerId: "player-1",
    });
    renderApp();

    expect(await screen.findByPlaceholderText("村のみんなに伝えること")).toHaveAttribute(
      "maxlength",
      "120",
    );
    expect(document.querySelector(".wa-app")).toHaveAttribute("data-message-max-chars", "120");
  });

  it("recovers from an operation error by refreshing server state", async () => {
    useUiStore.setState({
      activeGameId: "sample-game",
      activeView: "play",
      manualPlayerId: "player-1",
    });
    gameClientMock.submitAction.mockRejectedValueOnce(new Error("送信に失敗しました。"));
    renderApp();

    fireEvent.change(await screen.findByPlaceholderText("村のみんなに伝えること"), {
      target: { value: "確認します。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "決定する" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("送信に失敗しました。");
    expect(document.querySelector(".wa-app")).toHaveAttribute("data-operation-status", "failed");
    expect(document.querySelector(".wa-app")).toHaveAttribute("data-compact-layout", "false");
    const callsBeforeRecovery = gameClientMock.getScreen.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "最新状態を読み込む" }));

    await waitFor(() => {
      expect(gameClientMock.getScreen.mock.calls.length).toBeGreaterThan(callsBeforeRecovery);
    });
  });

  it("does not request a private player observation in observer mode", async () => {
    useUiStore.setState({
      activeGameId: "sample-game",
      activeView: "observe",
      manualPlayerId: "player-1",
    });

    renderApp();

    await screen.findByRole("heading", { name: "公開された記録" });
    expect(gameClientMock.getScreen).toHaveBeenCalledWith("sample-game", "");
    expect(gameClientMock.getScreen).not.toHaveBeenCalledWith("sample-game", "player-1");
  });
});
