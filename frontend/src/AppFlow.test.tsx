import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { useUiStore } from "./store/uiStore";
import { sampleScreenSource, sampleSetupOptions } from "./test/gameSamples";
import type { GameScreenSource } from "./gameClient/wireTypes";

const gameClientMock = vi.hoisted(() => ({
  advance: vi.fn(),
  createGame: vi.fn(),
  getReveal: vi.fn(),
  getScreen: vi.fn(),
  getSetupOptions: vi.fn(),
  listGames: vi.fn(),
  submitAction: vi.fn(),
}));

vi.mock("./data/SupabaseGameClient", () => ({
  gameClient: gameClientMock,
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

describe("App demo flow", () => {
  let currentScreen: GameScreenSource;

  beforeEach(() => {
    currentScreen = sampleScreenSource();
    gameClientMock.getSetupOptions.mockResolvedValue(sampleSetupOptions);
    gameClientMock.getScreen.mockImplementation(async () => currentScreen);
    gameClientMock.getReveal.mockResolvedValue(null);
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

  it("starts a playable Supabase village from setup choices", async () => {
    useUiStore.setState({
      activeGameId: null,
      activeView: "setup",
      manualPlayerId: "player-1",
    });
    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /月明かりの広場/ }));
    fireEvent.change(screen.getByLabelText("あなたの席"), { target: { value: "player-3" } });
    fireEvent.click(screen.getByRole("button", { name: /この村で始める/ }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "月明かりの広場" })).toBeInTheDocument();
    });
    expect(screen.getByText("あなた")).toBeInTheDocument();
    expect(screen.queryByText(/provider|model|token|game_id/i)).not.toBeInTheDocument();
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
});
