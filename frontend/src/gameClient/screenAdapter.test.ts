import { describe, expect, it } from "vitest";

import { sampleScreenSource } from "../test/gameSamples";
import { mapGameScreen } from "./screenAdapter";
import type { GameScreenSource } from "./wireTypes";

describe("mapGameScreen", () => {
  it("maps backend-shaped data into dawn table view models", async () => {
    const screen = mapGameScreen({
      screen: sampleScreenSource(),
      manualPlayerId: "player-1",
    });

    expect(screen.tableTitle).toBe("霧の村");
    expect(screen.phaseLabel).toBe("昼の議論");
    expect(screen.seats).toHaveLength(6);
    expect(screen.seats[0]).toMatchObject({
      displayName: "アオイ",
      isManual: true,
      seatTone: "self",
    });
    expect(screen.turnPanel.title).toBe("あなたの手番");
    expect(screen.turnPanel.actions[0]?.label).toBe("発言する");
    expect(screen.turnPanel.actions[0]?.requiresMessage).toBe(true);
    expect(screen.timeline[screen.timeline.length - 1]?.detail).toContain("温度差");
    expect(screen.observerRecord?.title).toBe("公開された記録");
    expect(screen.observerRecord?.lines.join(" ")).toContain("温度差");
  });

  it("does not put internal or secret fields into play timeline details", () => {
    const source: GameScreenSource = {
      state: {
        game_id: "secret-game",
        status: "running",
        phase: "day_discussion",
        day: 1,
        version: 1,
        seed: 1,
        narration_mode: "standard",
        players: [{ id: "player-1", name: "アオイ", alive: true, status: "alive" }],
        alive_player_ids: ["player-1"],
        eliminated_player_ids: [],
        winner: null,
        summary: {},
      },
      timeline: {
        game_id: "secret-game",
        next_after: 1,
        items: [
          {
            sequence: 1,
            event_sequence: 1,
            version: 1,
            phase: "day_discussion",
            day: 1,
            actor_id: "player-1",
            event_type: "speech",
            narration: null,
            payload: {
              message: "公開発言です",
              role: "werewolf",
              target_id: "player-2",
              token: "do-not-show",
              provider: "hidden",
              model: "hidden",
              game_id: "secret-game",
            },
            occurred_at: "2026-06-04T00:00:00Z",
          },
        ],
      },
      observation: null,
    };

    const screen = mapGameScreen({ screen: source, manualPlayerId: "player-1" });
    const text = screen.timeline.map((entry) => entry.detail).join(" ");

    expect(text).toContain("公開発言です");
    expect(text).not.toMatch(/werewolf|player-2|do-not-show|hidden|secret-game/);
  });
});
