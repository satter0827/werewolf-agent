import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocalDemoGameClient } from "../../../data/LocalDemoGameClient";
import { demoSetupOptions } from "../../../data/localDemoFixtures";
import { mapGameScreen } from "../../../gameClient/screenAdapter";
import { RoundTable } from "./RoundTable";
import { TurnPanel } from "./TurnPanel";
import { VillageSetup } from "./VillageSetup";
import { VillageTimeline } from "./VillageTimeline";

describe("village components", () => {
  it("renders setup choices with game-facing labels", async () => {
    render(<VillageSetup onCreate={() => undefined} setupOptions={demoSetupOptions} />);

    expect(screen.getByRole("heading", { name: "今夜の舞台を選ぶ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /この村で始める/ })).toBeInTheDocument();
    expect(screen.queryByText(/provider|model|API|token|game_id/i)).not.toBeInTheDocument();
  });

  it("renders round table seats and turn panel", async () => {
    const client = new LocalDemoGameClient();
    const model = mapGameScreen({
      screen: await client.getScreen("demo-game-1", "player-1"),
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
    expect(screen.getByRole("button", { name: /発言する/ })).toBeInTheDocument();
  });

  it("renders the public village timeline", async () => {
    const client = new LocalDemoGameClient();
    const model = mapGameScreen({
      screen: await client.getScreen("demo-game-1", "player-1"),
      manualPlayerId: "player-1",
    });

    render(<VillageTimeline entries={model.timeline} />);

    expect(screen.getByRole("heading", { name: "公開された出来事" })).toBeInTheDocument();
    expect(screen.getByText(/初日は発言の温度差/)).toBeInTheDocument();
  });
});
