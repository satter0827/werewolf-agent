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

const phaseLabels: Record<GamePhase, string> = {
  night: "夜の時間",
  day_discussion: "昼の議論",
  voting: "投票の時間",
  finished: "終幕",
};

const actionLabels: Record<string, string> = {
  speech: "発言する",
  vote: "投票する",
  seer_inspect: "占う",
  knight_guard: "守る",
  werewolf_attack: "襲撃する",
  pass: "少し待つ",
};

const actionDescriptions: Record<string, string> = {
  speech: "村のみんなに考えを伝えます",
  vote: "怪しいと思う相手を選びます",
  seer_inspect: "夜にひとりを調べます",
  knight_guard: "夜にひとりを守ります",
  werewolf_attack: "夜の行き先を選びます",
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
  const timeline = screen.timeline.items.map((item) => mapTimelineItem(item, actorNames));
  const observerRecord = mapObserverRecord(timeline);
  return {
    version: state.version,
    status: state.status,
    phase: state.phase,
    phaseLabel: phaseLabels[state.phase],
    dayLabel: state.phase === "night" ? `${state.day}日目の夜` : `${state.day}日目`,
    tableTitle: state.scenario_name ?? "霧の村",
    tableSubtitle: "朝焼けの広場で、村人たちが静かに向き合っています。",
    aliveCount: state.alive_player_ids.length,
    playerCount: state.players.length,
    winnerLabel: state.winner ? winnerLabel(state.winner) : null,
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
  if (payload === null || actions.length === 0) {
    return {
      title: "村を見守る",
      subtitle:
        state.phase === "finished" ? "この村の物語は終わりました" : "次の動きを待っています",
      roleHint: "見えている情報だけで推理します",
      visibleClues: ["公開された発言", "投票の流れ", "夜明けの結果"],
      actions: [
        {
          type: "advance",
          label: "夜明けを待つ",
          description: "村の動きを進めます",
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
    roleHint: visibleRole(payload) ? `あなたは ${friendlyRole(visibleRole(payload))}` : "村の一員です",
    visibleClues: visibleClues(payload, state),
    actions: actions.map((action) => ({
      type: action.type,
      label: actionLabels[action.type] ?? "行動する",
      description: actionDescriptions[action.type] ?? "この場でできることを選びます",
      enabled: true,
      requiresMessage: Boolean(action.message_required),
      targetOptions: (action.legal_targets ?? []).map((targetId) => ({
        id: targetId,
        label: state.players.find((player) => player.id === targetId)?.name ?? "村人",
      })),
    })),
  };
}

function visibleClues(payload: PlayerObservationPayload, state: PublicGameState): string[] {
  const known = Object.entries(payload.known_roles ?? {}).map(
    ([playerId, role]) =>
      `${state.players.find((player) => player.id === playerId)?.name ?? "誰か"} は ${friendlyRole(
        role,
      )} と分かっています`,
  );
  return known.length > 0 ? known : ["公開された発言", "これまでの投票", "今朝の出来事"];
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
): TimelineEntry {
  const publicPayload = Object.entries(item.payload)
    .filter(([key]) => !SECRET_FIELD_PATTERN.test(key))
    .map(([, value]) => String(value))
    .filter(Boolean);
  return {
    sequence: item.sequence,
    label: eventLabel(item.event_type),
    dayLabel: item.day ? `${item.day}日目` : "序章",
    actorName: item.actor_id ? actorNames.get(item.actor_id) ?? "村人" : "語り部",
    detail: item.narration ?? publicPayload.join(" / ") ?? "村に静かな変化がありました",
    tone: timelineTone(item.event_type),
  };
}

function mapObserverRecord(timeline: TimelineEntry[]): ObserverRecord {
  return {
    title: "公開された記録",
    lines: timeline.slice(-8).map((entry) => `${entry.dayLabel} ${entry.label}: ${entry.detail}`),
  };
}

function eventLabel(eventType: string): string {
  if (eventType.includes("vote")) return "投票";
  if (eventType.includes("night")) return "夜明け";
  if (eventType === "speech") return "発言";
  if (eventType.includes("created")) return "開幕";
  return "出来事";
}

function timelineTone(eventType: string): TimelineEntry["tone"] {
  if (eventType.includes("vote")) return "vote";
  if (eventType.includes("night")) return "night";
  if (eventType === "speech") return "speech";
  return "day";
}

function winnerLabel(winner: string): string {
  return winner === "villagers" ? "村人陣営の勝利" : "人狼陣営の勝利";
}

function friendlyRole(role: string): string {
  const labels: Record<string, string> = {
    villager: "村人",
    werewolf: "人狼",
    seer: "占い師",
    knight: "騎士",
  };
  return labels[role] ?? role;
}
