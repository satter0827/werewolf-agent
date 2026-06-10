import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { useUiStore } from "./store/uiStore";

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
  it("starts a playable local village from setup choices", async () => {
    useUiStore.setState({
      activeGameId: "demo-game-1",
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
      activeGameId: "demo-game-1",
      activeView: "play",
      manualPlayerId: "player-1",
    });
    renderApp();

    fireEvent.change(await screen.findByPlaceholderText("村のみんなに伝えること"), {
      target: { value: "今日はレンの投票理由を聞きたいです。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "決定する" }));

    await waitFor(() => {
      expect(screen.getByText("投票の時間")).toBeInTheDocument();
    });
    expect(screen.getByText("今日はレンの投票理由を聞きたいです。")).toBeInTheDocument();

    const targetSelect = screen.getByLabelText("相手を選ぶ") as HTMLSelectElement;
    const optionLabels = [...targetSelect.options].map((option) => option.textContent);
    expect(optionLabels).toContain("レン");
    expect(optionLabels).not.toContain("アオイ");
  });
});
