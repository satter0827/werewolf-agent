import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { mapGameScreen } from "../../../gameClient/screenAdapter";
import { sampleScreenSource, sampleSetupOptions } from "../../../test/gameSamples";
import { RoundTable } from "./RoundTable";
import { ObserverPanel } from "./ObserverPanel";
import { AuthPanel } from "./AuthPanel";
import { RecordsPanel } from "./RecordsPanel";
import { TurnPanel } from "./TurnPanel";
import { VillageSetup } from "./VillageSetup";
import { VillageTimeline } from "./VillageTimeline";

describe("village components", () => {
  it("renders setup choices with game-facing labels", async () => {
    render(
      <VillageSetup
        onCreate={() => undefined}
        setupOptions={sampleSetupOptions}
        uiSettings={{ default_manual_player_id: "player-1", default_setup_seed: "1" }}
      />,
    );

    expect(screen.getByRole("heading", { name: "遊び方を選ぶ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /この設定で始める/ })).toBeInTheDocument();
    expect(screen.queryByText(/provider|model|API|token|game_id/i)).not.toBeInTheDocument();
  });

  it("creates an observer game without assigning a private player seat", () => {
    const onCreate = vi.fn();
    render(
      <VillageSetup
        onCreate={onCreate}
        setupOptions={sampleSetupOptions}
        uiSettings={{ default_manual_player_id: "player-1", default_setup_seed: "1" }}
      />,
    );

    fireEvent.change(screen.getByLabelText("参加方法"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "観戦を始める" }));

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ manualPlayerId: "" }));
  });

  it("opens completed games from the records screen", () => {
    const onResumeGame = vi.fn();
    render(
      <RecordsPanel
        games={[
          {
            alive_count: 3,
            completed_at: "2026-07-24T00:10:00Z",
            created_at: "2026-07-24T00:00:00Z",
            day: 2,
            game_id: "completed-game",
            phase: "finished",
            player_count: 5,
            seed: 1,
            status: "completed",
            step_count: 6,
            turn_count: 12,
            updated_at: "2026-07-24T00:10:00Z",
            version: 7,
            winner: "village",
          },
        ]}
        onResumeGame={onResumeGame}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "結果を見る" }));

    expect(onResumeGame).toHaveBeenCalledWith("completed-game");
  });

  it("renders round table seats and turn panel", async () => {
    const model = mapGameScreen({
      screen: sampleScreenSource(),
      manualPlayerId: "player-1",
    });

    render(
      <>
        <RoundTable screen={model} />
        <TurnPanel onSubmit={() => undefined} panel={model.turnPanel} />
      </>,
    );

    expect(screen.getByText("アオイ")).toBeInTheDocument();
    expect(screen.getByText("あなた")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /発言/ })).toBeInTheDocument();
  });

  it("lets an observer owner advance a running game", () => {
    const model = mapGameScreen({ screen: sampleScreenSource(), manualPlayerId: "" });
    const onAdvance = vi.fn();

    render(<ObserverPanel isSubmitting={false} onAdvance={onAdvance} screen={model} />);
    fireEvent.click(screen.getByRole("button", { name: "進める" }));

    expect(onAdvance).toHaveBeenCalledOnce();
  });

  it("renders the public village timeline", async () => {
    const model = mapGameScreen({
      screen: sampleScreenSource(),
      manualPlayerId: "player-1",
    });

    render(<VillageTimeline entries={model.timeline} />);

    expect(screen.getByRole("heading", { name: "公開された出来事" })).toBeInTheDocument();
    expect(screen.getByText(/初日は発言の温度差/)).toBeInTheDocument();
  });

  it("offers constrained login fields to a guest", () => {
    render(
      <AuthPanel
        auth={{ email: null, isAnonymous: true, isAuthenticated: false }}
        isPending={false}
        onSignIn={() => undefined}
        onSignOut={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

    expect(screen.getByLabelText("メールアドレス")).toHaveAttribute("maxlength", "254");
    expect(screen.getByLabelText("パスワード")).toHaveAttribute("minlength", "8");
  });
});
