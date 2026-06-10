import type { GameClient, SubmitPlayerActionCommand } from "../gameClient/GameClient";
import type {
  AvailableAction,
  CreateGameRequest,
  GameListResponse,
  GamePhase,
  GameResponse,
  GameRevealResponse,
  GameScreenSource,
  GameSetupOptionsResponse,
  GameTimelineItem,
  PlayerActionResponse,
  PlayerObservationResponse,
  PublicGameState,
  PublicGameSummary,
  PublicPlayerState,
} from "../gameClient/wireTypes";
import {
  demoNow,
  demoPlayers,
  demoRoleAssignments,
  demoSetupOptions,
} from "./localDemoFixtures";

interface LocalGameRecord {
  manualPlayerId: string;
  manualToken: string;
  reveal: GameRevealResponse;
  state: PublicGameState;
  timeline: GameTimelineItem[];
}

const completedSummary: PublicGameSummary = {
  game_id: "completed-village",
  status: "completed",
  phase: "finished",
  day: 3,
  version: 19,
  seed: 41,
  player_count: 6,
  alive_count: 3,
  winner: "villagers",
  step_count: 19,
  turn_count: 16,
  created_at: demoNow,
  updated_at: demoNow,
  completed_at: demoNow,
};

export class LocalDemoGameClient implements GameClient {
  private activeGameId = "demo-game-1";
  private readonly games = new Map<string, LocalGameRecord>();

  constructor() {
    const initial = this.buildGame({
      manualPlayerId: "player-1",
      request: {
        seed: 17,
        scenario_id: "misty-village",
        setup_preset_id: "classic-six",
        role_counts: demoSetupOptions.default_role_counts,
        manual_player_id: "player-1",
        rules: demoSetupOptions.default_rules,
      },
    });
    this.games.set(initial.state.game_id, initial);
  }

  async getSetupOptions(): Promise<GameSetupOptionsResponse> {
    return structuredClone(demoSetupOptions);
  }

  async createGame(request: CreateGameRequest): Promise<GameResponse> {
    const manualPlayerId = request.manual_player_id ?? "player-1";
    const record = this.buildGame({ manualPlayerId, request });
    this.games.set(record.state.game_id, record);
    this.activeGameId = record.state.game_id;
    return {
      game_id: record.state.game_id,
      state: structuredClone(record.state),
      manual_player: {
        player_id: manualPlayerId,
        token: record.manualToken,
      },
    };
  }

  async getScreen(gameId: string | null, manualPlayerId: string): Promise<GameScreenSource> {
    const record = this.requireGame(gameId);
    return {
      state: structuredClone(record.state),
      timeline: {
        game_id: record.state.game_id,
        items: structuredClone(record.timeline),
        next_after: record.timeline.length,
      },
      observation: this.observation(record, manualPlayerId),
      reveal: null,
    };
  }

  async getReveal(gameId: string): Promise<GameRevealResponse> {
    return structuredClone(this.requireGame(gameId).reveal);
  }

  async listGames(): Promise<GameListResponse> {
    const activeGames = [...this.games.values()].map((record) => this.summary(record));
    return { games: [...activeGames, completedSummary], next_offset: null };
  }

  async submitAction(command: SubmitPlayerActionCommand): Promise<PlayerActionResponse> {
    const record = this.requireGame(command.gameId);
    this.applyManualAction(record, command);
    this.syncReveal(record);
    return {
      accepted: true,
      game_id: record.state.game_id,
      state: structuredClone(record.state),
    };
  }

  async advance({ gameId }: { gameId: string }): Promise<GameScreenSource> {
    const record = this.requireGame(gameId);
    this.appendTimeline(record, {
      actor_id: "player-3",
      event_type: "speech",
      narration: "ミナは、投票の流れをもう一度見たいと言いました。",
      payload: { message: "投票の流れをもう一度見たいです。" },
    });
    this.syncReveal(record);
    return this.getScreen(gameId, record.manualPlayerId);
  }

  getManualTokenForTest(gameId: string): string | null {
    return this.games.get(gameId)?.manualToken ?? null;
  }

  private buildGame({
    manualPlayerId,
    request,
  }: {
    manualPlayerId: string;
    request: CreateGameRequest;
  }): LocalGameRecord {
    const gameId = `demo-game-${this.games.size + 1}`;
    const scenario = demoSetupOptions.scenarios.find((item) => item.id === request.scenario_id);
    const players = structuredClone(demoPlayers);
    const state: PublicGameState = {
      game_id: gameId,
      status: "running",
      phase: "day_discussion",
      day: 1,
      version: 1,
      seed: request.seed,
      scenario_id: request.scenario_id,
      scenario_name: scenario?.name ?? "霧の村",
      narration_mode: demoSetupOptions.default_narration_mode,
      players,
      alive_player_ids: players.map((player) => player.id),
      eliminated_player_ids: [],
      winner: null,
      summary: { public_note: "6人が生存しています" },
      created_at: demoNow,
      updated_at: demoNow,
    };
    const record: LocalGameRecord = {
      manualPlayerId,
      manualToken: `manual-${gameId}-${manualPlayerId}`,
      state,
      timeline: [],
      reveal: this.initialReveal({ gameId, manualPlayerId, request, state }),
    };
    this.appendTimeline(record, {
      actor_id: null,
      event_type: "game_created",
      narration: `${state.scenario_name}に、静かな朝が訪れました。`,
      payload: {},
    });
    this.appendTimeline(record, {
      actor_id: "player-2",
      event_type: "speech",
      narration: "初日は発言の温度差を見たいです。",
      payload: { message: "初日は発言の温度差を見たいです。" },
    });
    return record;
  }

  private initialReveal({
    gameId,
    request,
    state,
  }: {
    gameId: string;
    manualPlayerId: string;
    request: CreateGameRequest;
    state: PublicGameState;
  }): GameRevealResponse {
    return {
      game_id: gameId,
      status: state.status,
      phase: state.phase,
      day: state.day,
      version: state.version,
      seed: state.seed,
      scenario_id: state.scenario_id,
      scenario_name: state.scenario_name,
      narration_mode: state.narration_mode,
      role_counts: request.role_counts,
      rules: request.rules ?? demoSetupOptions.default_rules,
      players: state.players.map((player) => ({
        id: player.id,
        name: player.name,
        role: demoRoleAssignments[player.id] ?? "villager",
        faction: factionForRole(demoRoleAssignments[player.id]),
        alive: player.alive,
        status: player.status,
      })),
      alive_player_ids: [...state.alive_player_ids],
      eliminated_player_ids: [],
      winner: null,
      pending_votes: [],
      pending_night_actions: [],
      votes: [],
      nights: [],
    };
  }

  private observation(
    record: LocalGameRecord,
    manualPlayerId: string,
  ): PlayerObservationResponse | null {
    if (record.state.status === "completed") {
      return null;
    }
    const manualPlayer = record.state.players.find((player) => player.id === manualPlayerId);
    if (!manualPlayer?.alive) {
      return null;
    }
    return {
      player_id: manualPlayerId,
      phase: record.state.phase,
      day: record.state.day,
      role: demoRoleAssignments[manualPlayerId] ?? "villager",
      known_roles: manualPlayerId === "player-1" ? { "player-5": "villager" } : {},
      available_actions: this.availableActions(record, manualPlayerId),
    };
  }

  private availableActions(record: LocalGameRecord, playerId: string): AvailableAction[] {
    const legalTargets = record.state.players
      .filter((player) => player.alive && player.id !== playerId)
      .map((player) => player.id);
    if (record.state.phase === "day_discussion") {
      return [{ type: "speech", message_required: true }];
    }
    if (record.state.phase === "voting") {
      return [{ type: "vote", legal_targets: legalTargets }];
    }
    if (record.state.phase === "night") {
      return [{ type: "seer_inspect", legal_targets: legalTargets }];
    }
    return [];
  }

  private applyManualAction(record: LocalGameRecord, command: SubmitPlayerActionCommand): void {
    const action = command.action;
    if (action.type === "speech") {
      const message = action.message?.trim() || "私は、投票の理由をもう少し聞きたいです。";
      this.appendTimeline(record, {
        actor_id: command.playerId,
        event_type: "speech",
        narration: message,
        payload: { message },
      });
      this.appendTimeline(record, {
        actor_id: "player-5",
        event_type: "speech",
        narration: "ユイは、発言の流れにうなずきました。",
        payload: { message: "その見方は自然だと思います。" },
      });
      this.setPhase(record, "voting");
      return;
    }
    if (action.type === "vote") {
      const targetId = action.target_id ?? this.firstLegalTarget(record, command.playerId);
      const targetName = playerName(record.state.players, targetId);
      this.appendTimeline(record, {
        actor_id: command.playerId,
        event_type: "vote_submitted",
        narration: `${targetName}に票が入りました。`,
        payload: { vote_label: targetName },
      });
      this.appendTimeline(record, {
        actor_id: null,
        event_type: "vote_resolved",
        narration: "投票は割れ、村は夜を迎えました。",
        payload: { result: "夜を迎える" },
      });
      record.reveal.votes.push({
        day: record.state.day,
        votes: { [command.playerId]: targetId },
        counts: { [targetId]: 1 },
        tied_player_ids: [],
        missing_voter_ids: [],
        eliminated_player_id: null,
        tie_break_policy: "no_elimination",
      });
      this.setPhase(record, "night");
      return;
    }
    if (action.type === "seer_inspect" || action.type === "knight_guard") {
      const targetId = action.target_id ?? this.firstLegalTarget(record, command.playerId);
      const killedPlayer = this.firstAlivePlayerExcept(record, [command.playerId, targetId]);
      if (killedPlayer) {
        killedPlayer.alive = false;
        killedPlayer.status = "dead";
        killedPlayer.killed_night = record.state.day;
        record.state.alive_player_ids = record.state.players
          .filter((player) => player.alive)
          .map((player) => player.id);
        record.state.eliminated_player_ids = record.state.players
          .filter((player) => !player.alive)
          .map((player) => player.id);
      }
      this.appendTimeline(record, {
        actor_id: null,
        event_type: "night_resolved",
        narration: killedPlayer
          ? `夜明けに${killedPlayer.name}の姿がありませんでした。`
          : "静かな夜が明け、全員が広場に戻りました。",
        payload: killedPlayer ? { killed_player_name: killedPlayer.name } : { result: "平和な朝" },
      });
      record.reveal.nights.push({
        day: record.state.day,
        attacked_player_id: killedPlayer?.id ?? null,
        protected_player_id: action.type === "knight_guard" ? targetId : null,
        killed_player_id: killedPlayer?.id ?? null,
      });
      record.state.day += 1;
      this.setPhase(record, "day_discussion");
      return;
    }
    this.setPhase(record, "day_discussion");
  }

  private appendTimeline(
    record: LocalGameRecord,
    item: Pick<GameTimelineItem, "actor_id" | "event_type" | "narration" | "payload">,
  ): void {
    const sequence = record.timeline.length + 1;
    record.state.version += 1;
    record.state.updated_at = demoNow;
    record.timeline.push({
      sequence,
      event_sequence: sequence,
      version: record.state.version,
      phase: record.state.phase,
      day: record.state.day,
      actor_id: item.actor_id,
      event_type: item.event_type,
      narration: item.narration,
      payload: item.payload,
      occurred_at: demoNow,
    });
  }

  private setPhase(record: LocalGameRecord, phase: GamePhase): void {
    record.state.phase = phase;
    record.state.version += 1;
    record.state.updated_at = demoNow;
  }

  private syncReveal(record: LocalGameRecord): void {
    record.reveal = {
      ...record.reveal,
      status: record.state.status,
      phase: record.state.phase,
      day: record.state.day,
      version: record.state.version,
      alive_player_ids: [...record.state.alive_player_ids],
      eliminated_player_ids: [...record.state.eliminated_player_ids],
      players: record.reveal.players.map((player) => {
        const publicPlayer = record.state.players.find((item) => item.id === player.id);
        return {
          ...player,
          alive: publicPlayer?.alive ?? player.alive,
          status: publicPlayer?.status ?? player.status,
        };
      }),
    };
  }

  private summary(record: LocalGameRecord): PublicGameSummary {
    return {
      game_id: record.state.game_id,
      status: record.state.status,
      phase: record.state.phase,
      day: record.state.day,
      version: record.state.version,
      seed: record.state.seed,
      player_count: record.state.players.length,
      alive_count: record.state.alive_player_ids.length,
      winner: record.state.winner,
      step_count: record.state.version,
      turn_count: record.timeline.length,
      created_at: record.state.created_at ?? demoNow,
      updated_at: record.state.updated_at ?? demoNow,
      completed_at: null,
    };
  }

  private requireGame(gameId: string | null): LocalGameRecord {
    const id = gameId ?? this.activeGameId;
    const record = this.games.get(id);
    if (!record) {
      throw new Error("Demo game is not available.");
    }
    return record;
  }

  private firstLegalTarget(record: LocalGameRecord, playerId: string): string {
    return (
      record.state.players.find((player) => player.alive && player.id !== playerId)?.id ??
      playerId
    );
  }

  private firstAlivePlayerExcept(record: LocalGameRecord, excludedIds: string[]): PublicPlayerState | null {
    return (
      record.state.players.find(
        (player) => player.alive && !excludedIds.includes(player.id),
      ) ?? null
    );
  }
}

export const localDemoGameClient = new LocalDemoGameClient();

function factionForRole(role: string | undefined): string {
  return role === "werewolf" ? "werewolves" : "villagers";
}

function playerName(players: PublicPlayerState[], playerId: string): string {
  return players.find((player) => player.id === playerId)?.name ?? "誰か";
}
