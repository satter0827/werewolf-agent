import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mapGameScreen } from "../../../gameClient/screenAdapter";
import { sampleScreenSource, sampleSetupOptions } from "../../../test/gameSamples";
import { RoundTable } from "./RoundTable";
import { TurnPanel } from "./TurnPanel";
import { VillageSetup } from "./VillageSetup";
import { VillageTimeline } from "./VillageTimeline";

describe("village components", () => {
  it("renders setup choices with game-facing labels", async () => {
    render(<VillageSetup onCreate={() => undefined} setupOptions={sampleSetupOptions} />);

    expect(screen.getByRole("heading", { name: "今夜の舞台を選ぶ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /この村で始める/ })).toBeInTheDocument();
    expect(screen.queryByText(/provider|model|API|token|game_id/i)).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /発言する/ })).toBeInTheDocument();
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
});
