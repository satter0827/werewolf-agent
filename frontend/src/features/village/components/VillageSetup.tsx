import { Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  generatedSeatOptions,
  playerCountFromRoles,
  roleCountsForSetup,
  roleLabel,
} from "../../../gameClient/setupOptions";
import type { GameSetupOptionsResponse } from "../../../gameClient/wireTypes";
import type { SetupDraft } from "../../../gameClient/uiTypes";
import type { PublicRuntimeConfig } from "../../../gameClient/GameClient";

interface VillageSetupProps {
  isCreating?: boolean;
  onCreate: (draft: SetupDraft) => void;
  setupOptions: GameSetupOptionsResponse;
  uiSettings: Pick<PublicRuntimeConfig["ui"], "default_manual_player_id" | "default_setup_seed">;
}

export function VillageSetup({
  isCreating = false,
  onCreate,
  setupOptions,
  uiSettings,
}: VillageSetupProps) {
  const defaultPlayerId = uiSettings.default_manual_player_id;
  const defaultSeed = uiSettings.default_setup_seed;
  const [draft, setDraft] = useState<SetupDraft>({
    setupPresetId: setupOptions.default_setup_preset_id ?? setupOptions.setup_presets[0]?.id ?? "",
    manualPlayerId: defaultPlayerId,
    seed: defaultSeed,
  });
  const selectedRoleCounts = useMemo(
    () => roleCountsForSetup(setupOptions, draft.setupPresetId),
    [draft.setupPresetId, setupOptions.setup_presets],
  );
  const seatOptions = useMemo(
    () => generatedSeatOptions(playerCountFromRoles(selectedRoleCounts)),
    [selectedRoleCounts],
  );

  useEffect(() => {
    if (!draft.manualPlayerId || seatOptions.some((seat) => seat.id === draft.manualPlayerId)) {
      return;
    }
    setDraft((current) => ({
      ...current,
      manualPlayerId: seatOptions[0]?.id ?? defaultPlayerId,
    }));
  }, [defaultPlayerId, draft.manualPlayerId, seatOptions]);

  return (
    <section className="wa-setup" aria-label="ゲームを作る">
      <div className="wa-setup-main">
        <p className="wa-kicker">ゲームを作る</p>
        <h2>遊び方を選ぶ</h2>
        <div className="wa-scenario-grid">
          {setupOptions.setup_presets.map((preset) => {
            const scenario = setupOptions.scenarios.find(
              (candidate) => candidate.id === preset.scenario_id,
            );
            return (
              <button
                className={
                  preset.id === draft.setupPresetId
                    ? "wa-scenario wa-scenario-selected"
                    : "wa-scenario"
                }
                key={preset.id}
                onClick={() => setDraft((current) => ({ ...current, setupPresetId: preset.id }))}
                type="button"
              >
                <strong>{preset.name}</strong>
                <span>
                  {scenario ? `${scenario.name} — ${scenario.summary}` : preset.scenario_id}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <aside className="wa-setup-side">
        <label>
          選択中の遊び方
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
          参加方法
          <select
            value={draft.manualPlayerId}
            onChange={(event) =>
              setDraft((current) => ({ ...current, manualPlayerId: event.target.value }))
            }
          >
            <option value="">観戦する</option>
            {seatOptions.map((seat) => (
              <option key={seat.id} value={seat.id}>
                {seat.label}
              </option>
            ))}
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
          {Object.entries(selectedRoleCounts).map(([role, count]) => (
            <span key={role}>
              {roleLabel(role, setupOptions)} {count}
            </span>
          ))}
        </div>
        <button
          className="wa-primary-action"
          disabled={isCreating}
          onClick={() => onCreate(draft)}
          type="button"
        >
          <Play size={18} aria-hidden="true" />
          {isCreating
            ? "ゲームを準備中"
            : draft.manualPlayerId
              ? "この設定で始める"
              : "観戦を始める"}
        </button>
      </aside>
    </section>
  );
}
