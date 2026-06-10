import { Play } from "lucide-react";
import { useMemo, useState } from "react";

import type { GameSetupOptionsResponse } from "../../../gameClient/wireTypes";
import type { SetupDraft } from "../../../gameClient/uiTypes";

interface VillageSetupProps {
  isCreating?: boolean;
  onCreate: (draft: SetupDraft) => void;
  setupOptions: GameSetupOptionsResponse;
}

export function VillageSetup({ isCreating = false, onCreate, setupOptions }: VillageSetupProps) {
  const [draft, setDraft] = useState<SetupDraft>({
    scenarioId: setupOptions.default_scenario_id ?? setupOptions.scenarios[0]?.id ?? "",
    setupPresetId:
      setupOptions.default_setup_preset_id ?? setupOptions.setup_presets[0]?.id ?? "",
    manualPlayerId: "player-1",
    seed: "17",
  });
  const selectedPreset = useMemo(
    () => setupOptions.setup_presets.find((preset) => preset.id === draft.setupPresetId),
    [draft.setupPresetId, setupOptions.setup_presets],
  );

  return (
    <section className="wa-setup" aria-label="村を作る">
      <div className="wa-setup-main">
        <p className="wa-kicker">村を作る</p>
        <h2>今夜の舞台を選ぶ</h2>
        <div className="wa-scenario-grid">
          {setupOptions.scenarios.map((scenario) => (
            <button
              className={
                scenario.id === draft.scenarioId
                  ? "wa-scenario wa-scenario-selected"
                  : "wa-scenario"
              }
              key={scenario.id}
              onClick={() => setDraft((current) => ({ ...current, scenarioId: scenario.id }))}
              type="button"
            >
              <strong>{scenario.name}</strong>
              <span>{scenario.description}</span>
            </button>
          ))}
        </div>
      </div>

      <aside className="wa-setup-side">
        <label>
          配役
          <select
            value={draft.setupPresetId}
            onChange={(event) =>
              setDraft((current) => ({ ...current, setupPresetId: event.target.value }))
            }
          >
            {setupOptions.setup_presets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          あなたの席
          <select
            value={draft.manualPlayerId}
            onChange={(event) =>
              setDraft((current) => ({ ...current, manualPlayerId: event.target.value }))
            }
          >
            {Array.from({ length: 6 }, (_, index) => {
              const playerId = `player-${index + 1}`;
              return (
                <option key={playerId} value={playerId}>
                  {index + 1}番席
                </option>
              );
            })}
          </select>
        </label>
        <label>
          合言葉
          <input
            inputMode="numeric"
            value={draft.seed}
            onChange={(event) => setDraft((current) => ({ ...current, seed: event.target.value }))}
          />
        </label>
        <div className="wa-role-counts">
          {Object.entries(selectedPreset?.role_counts ?? setupOptions.default_role_counts).map(
            ([role, count]) => (
              <span key={role}>
                {roleLabel(role)} {count}
              </span>
            ),
          )}
        </div>
        <button
          className="wa-primary-action"
          disabled={isCreating}
          onClick={() => onCreate(draft)}
          type="button"
        >
          <Play size={18} aria-hidden="true" />
          {isCreating ? "村を準備中" : "この村で始める"}
        </button>
      </aside>
    </section>
  );
}

function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    villager: "村人",
    werewolf: "人狼",
    seer: "占い師",
    knight: "騎士",
  };
  return labels[role] ?? role;
}
