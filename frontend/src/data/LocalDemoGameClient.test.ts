import { describe, expect, it } from "vitest";

import { LocalDemoGameClient } from "./LocalDemoGameClient";
import { demoSetupOptions } from "./localDemoFixtures";

describe("LocalDemoGameClient", () => {
  it("creates a local game from setup input and stores the manual credential internally", async () => {
    const client = new LocalDemoGameClient();

    const response = await client.createGame({
      seed: 88,
      scenario_id: "moon-plaza",
      setup_preset_id: "classic-six",
      role_counts: demoSetupOptions.default_role_counts,
      manual_player_id: "player-3",
      rules: demoSetupOptions.default_rules,
    });
    const screen = await client.getScreen(response.game_id, "player-3");

    expect(response.manual_player?.player_id).toBe("player-3");
    expect(client.getManualTokenForTest(response.game_id)).toContain("manual-");
    expect(screen.state.scenario_name).toBe("月明かりの広場");
    expect(screen.state.seed).toBe(88);
    expect(screen.observation?.player_id).toBe("player-3");
  });

  it("updates timeline, phase, and available actions after manual actions", async () => {
    const client = new LocalDemoGameClient();

    await client.submitAction({
      gameId: "demo-game-1",
      playerId: "player-1",
      action: { type: "speech", message: "今日はレンの投票理由を聞きたいです。" },
    });
    const afterSpeech = await client.getScreen("demo-game-1", "player-1");

    expect(afterSpeech.state.phase).toBe("voting");
    expect(afterSpeech.timeline.items[afterSpeech.timeline.items.length - 2]?.narration).toContain(
      "レンの投票理由",
    );
    expect(afterSpeech.observation?.available_actions[0]?.type).toBe("vote");

    await client.submitAction({
      gameId: "demo-game-1",
      playerId: "player-1",
      action: { type: "vote", target_id: "player-2" },
    });
    const afterVote = await client.getScreen("demo-game-1", "player-1");

    expect(afterVote.state.phase).toBe("night");
    expect(afterVote.observation?.available_actions[0]?.type).toBe("seer_inspect");
    expect(afterVote.observation?.available_actions[0]?.legal_targets).toContain("player-2");
  });
});
