import type { GamePhase, GameStatus, PlayerActionRequest, PublicGameSummary, Winner } from "./wireTypes";

export type ViewId = "setup" | "play" | "observe" | "records";
export type SkinId = "dawn_table";

export interface SkinDefinition {
  id: SkinId;
  name: string;
  density: "comfortable";
  layout: {
    desktopColumns: string;
    mobileOrder: string[];
  };
  tokens: Record<string, string>;
}

export interface RoundTableSeat {
  id: string;
  displayName: string;
  portraitKey: string;
  alive: boolean;
  currentMood: string;
  lastPublicLine: string;
  isManual: boolean;
  isCurrentTurn: boolean;
  seatTone: "self" | "active" | "quiet" | "down";
}

export interface TurnAction {
  type: PlayerActionRequest["type"] | "advance";
  label: string;
  description: string;
  enabled: boolean;
  requiresMessage: boolean;
  targetOptions: Array<{ id: string; label: string }>;
}

export interface TurnActionSubmit {
  message?: string;
  targetId?: string;
  type: TurnAction["type"];
}

export interface TurnPanelModel {
  title: string;
  subtitle: string;
  roleHint: string;
  visibleClues: string[];
  actions: TurnAction[];
}

export interface TimelineEntry {
  sequence: number;
  label: string;
  dayLabel: string;
  actorName: string;
  detail: string;
  tone: "day" | "night" | "vote" | "speech" | "system";
}

export interface ObserverRecord {
  title: string;
  lines: string[];
}

export interface GameScreenModel {
  status: GameStatus;
  phase: GamePhase;
  phaseLabel: string;
  dayLabel: string;
  tableTitle: string;
  tableSubtitle: string;
  aliveCount: number;
  playerCount: number;
  winnerLabel: string | null;
  seats: RoundTableSeat[];
  turnPanel: TurnPanelModel;
  timeline: TimelineEntry[];
  observerRecord: ObserverRecord | null;
}

export interface SetupDraft {
  scenarioId: string;
  setupPresetId: string;
  manualPlayerId: string;
  seed: string;
}

export interface RecordsModel {
  games: PublicGameSummary[];
}

export type { PublicGameSummary, Winner };
