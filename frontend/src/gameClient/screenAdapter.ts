import type {
  AvailableAction,
  GamePhase,
  GameScreenSource,
  GameTimelineItem,
  PlayerActionRequest,
  PlayerObservationPayload,
  PlayerObservationResponse,
  PublicGameState,
} from "./wireTypes";
import type {
  GameScreenModel,
  ObserverRecord,
  RoundTableSeat,
  TimelineEntry,
  TurnAction,
  TurnPanelModel,
} from "./uiTypes";

const SECRET_FIELD_PATTERN = /(role|target|token|provider|model|trace|game_id|api|secret)/i;

const fallbackPhaseLabels: Record<GamePhase, string> = {
  night: "夜の時間",
  day_discussion: "昼の議論",
  voting: "投票の時間",
  finished: "終幕",
};

const fallbackActionLabels: Record<string, string> = {
  speech: "発言する",
  vote: "投票する",
  seer_inspect: "占う",
  knight_guard: "守る",
  werewolf_attack: "襲撃する",
  pass: "少し待つ",
};

const actionDescriptions: Record<string, string> = {
  speech: "参加者へ考えを伝えます",
  vote: "対象をひとり選びます",
  seer_inspect: "夜にひとりを調べます",
  knight_guard: "ひとりを守ります",
  werewolf_attack: "夜の対象を選びます",
  pass: "今は行動を見送ります",
};

export function mapGameScreen({
  screen,
  manualPlayerId,
}: {
  screen: GameScreenSource;
  manualPlayerId: string;
}): GameScreenModel {
  const state = screen.state;
  const actorNames = new Map(state.players.map((player) => [player.id, player.name]));
  const seats = mapSeats(state, screen.timeline.items, manualPlayerId);
  const timeline = screen.timeline.items.map((item) => mapTimelineItem(item, actorNames, state));
  const observerRecord = mapObserverRecord(timeline);
  const phaseLabel = themeTerm(state, "phase_names", state.phase, fallbackPhaseLabels[state.phase]);
  return {
    version: state.version,
    status: state.status,
    phase: state.phase,
    phaseLabel,
    dayLabel: `${state.day}日目・${phaseLabel}`,
    tableTitle: state.scenario_name ?? "ゲーム",
    tableSubtitle: state.theme?.premise ?? "公開情報を手がかりに、隠れた脅威を探します。",
    storyThemeId: state.theme?.id ?? null,
    aliveCount: state.alive_player_ids.length,
    playerCount: state.players.length,
    winnerLabel: state.winner ? winnerLabel(state, state.winner) : null,
    seats,
    turnPanel: mapTurnPanel(screen.observation, state),
    timeline,
    observerRecord,
  };
}

function mapSeats(
  state: PublicGameState,
  timeline: GameTimelineItem[],
  manualPlayerId: string,
): RoundTableSeat[] {
  const currentActorId = [...timeline].reverse().find((item) => item.actor_id)?.actor_id;
  return state.players.map((player, index) => {
    const isManual = player.id === manualPlayerId;
    const isCurrentTurn = player.id === currentActorId;
    return {
      id: player.id,
      displayName: player.name,
      portraitKey: `portrait-${index + 1}`,
      alive: player.alive,
      currentMood: player.alive ? (isCurrentTurn ? "発言中" : "様子を見る") : "退場",
      lastPublicLine: lastPublicLine(timeline, player.id),
      isManual,
      isCurrentTurn,
      seatTone: !player.alive ? "down" : isManual ? "self" : isCurrentTurn ? "active" : "quiet",
    };
  });
}

function lastPublicLine(timeline: GameTimelineItem[], playerId: string): string {
  const speech = [...timeline]
    .reverse()
    .find((item) => item.actor_id === playerId && item.event_type === "speech");
  if (speech?.narration) {
    return speech.narration;
  }
  return "まだ大きな動きはありません";
}

function mapTurnPanel(
  observation: PlayerObservationResponse | null,
  state: PublicGameState,
): TurnPanelModel {
  const payload = observation?.observation ?? null;
  const actions = normalizeActions(payload);
  if (state.phase === "finished") {
    return {
      title: "ゲームを振り返る",
      subtitle: "この物語は終わりました",
      roleHint: "公開された記録から結末を振り返ります",
      visibleClues: defaultClues(state),
      actions: [],
    };
  }
  if (payload === null || actions.length === 0) {
    return {
      title: "ゲームを見守る",
      subtitle: "次の動きを待っています",
      roleHint: "見えている情報だけで推理します",
      visibleClues: defaultClues(state),
      actions: [
        {
          type: "advance",
          label: "進行を待つ",
          description: "ゲームを次の状態へ進めます",
          enabled: true,
          requiresMessage: false,
          targetOptions: [],
        },
      ],
    };
  }
  return {
    title: "あなたの手番",
    subtitle: "今できる行動を選んでください",
    roleHint: visibleRole(payload)
      ? `あなたは ${friendlyRole(state, visibleRole(payload))}`
      : "あなたも参加者のひとりです",
    visibleClues: visibleClues(payload, state),
    actions: actions.map((action) => ({
      type: action.type,
      label: themeTerm(
        state,
        "action_names",
        action.type,
        fallbackActionLabels[action.type] ?? "行動する",
      ),
      description:
        actionDescriptions[action.type] ??
        `${themeTerm(state, "action_names", action.type, "行動")}を実行します`,
      enabled: true,
      requiresMessage: Boolean(action.message_required),
      targetOptions: (action.legal_targets ?? []).map((targetId) => ({
        id: targetId,
        label: state.players.find((player) => player.id === targetId)?.name ?? "参加者",
      })),
    })),
  };
}

function visibleClues(payload: PlayerObservationPayload, state: PublicGameState): string[] {
  const known = Object.entries(payload.known_roles ?? {}).map(
    ([playerId, role]) =>
      `${state.players.find((player) => player.id === playerId)?.name ?? "誰か"} は ${friendlyRole(state, role)} と分かっています`,
  );
  return known.length > 0 ? known : defaultClues(state);
}

function defaultClues(state: PublicGameState): string[] {
  return [
    `公開された${themeTerm(state, "action_names", "speech", "発言")}`,
    `これまでの${themeTerm(state, "action_names", "vote", "投票")}`,
    `${themeTerm(state, "phase_names", "night", "夜")}の結果`,
  ];
}

function normalizeActions(payload: PlayerObservationPayload | null): AvailableAction[] {
  if (payload === null) {
    return [];
  }
  const targetMap = payload.legal_targets ?? {};
  return (payload.available_actions ?? []).map((action) => {
    if (typeof action === "string") {
      const actionType = action as PlayerActionRequest["type"];
      return {
        type: actionType,
        legal_targets: targetMap[actionType] ?? [],
        message_required: actionType === "speech",
      };
    }
    return action;
  });
}

function visibleRole(payload: PlayerObservationPayload): string {
  return String(payload.me?.role ?? payload.role ?? "");
}

function mapTimelineItem(
  item: GameTimelineItem,
  actorNames: Map<string, string>,
  state: PublicGameState,
): TimelineEntry {
  const publicPayload = Object.entries(item.payload)
    .filter(([key]) => !SECRET_FIELD_PATTERN.test(key))
    .map(([, value]) => String(value))
    .filter(Boolean);
  return {
    sequence: item.sequence,
    label: eventLabel(item.event_type, state),
    dayLabel: item.day ? `${item.day}日目` : "序章",
    actorName: item.actor_id ? (actorNames.get(item.actor_id) ?? "参加者") : "記録",
    detail: item.narration ?? publicPayload.join(" / ") ?? "状況に変化がありました",
    tone: timelineTone(item.event_type),
  };
}

function mapObserverRecord(timeline: TimelineEntry[]): ObserverRecord {
  return {
    title: "公開された記録",
    entries: timeline.slice(-8).map((entry) => ({
      sequence: entry.sequence,
      text: `${entry.dayLabel} ${entry.label}: ${entry.detail}`,
    })),
  };
}

function eventLabel(eventType: string, state: PublicGameState): string {
  if (eventType.includes("vote")) return themeTerm(state, "action_names", "vote", "投票");
  if (eventType.includes("night")) return themeTerm(state, "phase_names", "night", "夜");
  if (eventType === "speech" || eventType === "speech_recorded") {
    return themeTerm(state, "action_names", "speech", "発言");
  }
  if (eventType.includes("created")) return "開幕";
  return "出来事";
}

function timelineTone(eventType: string): TimelineEntry["tone"] {
  if (eventType.includes("vote")) return "vote";
  if (eventType.includes("night")) return "night";
  if (eventType === "speech") return "speech";
  return "day";
}

function winnerLabel(state: PublicGameState, winner: string): string {
  return `${themeTerm(state, "faction_names", winner, winner)}の勝利`;
}

function friendlyRole(state: PublicGameState, role: string): string {
  const fallbackLabels: Record<string, string> = {
    villager: "村人",
    werewolf: "人狼",
    seer: "占い師",
    knight: "騎士",
  };
  return themeTerm(state, "role_names", role, fallbackLabels[role] ?? role);
}

function themeTerm(
  state: PublicGameState,
  field: "role_names" | "faction_names" | "action_names" | "phase_names",
  conceptId: string,
  fallback: string,
): string {
  return state.theme?.[field]?.[conceptId] ?? fallback;
}
