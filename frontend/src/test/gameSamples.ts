import type {
  GameScreenSource,
  GameSetupOptionsResponse,
  PublicPlayerState,
} from "../gameClient/wireTypes";

export const sampleNow = "2026-06-04T00:00:00Z";

export const samplePlayers: PublicPlayerState[] = [
  { id: "player-1", name: "アオイ", alive: true, status: "alive" },
  { id: "player-2", name: "レン", alive: true, status: "alive" },
  { id: "player-3", name: "ミナ", alive: true, status: "alive" },
  { id: "player-4", name: "ソウ", alive: true, status: "alive" },
  { id: "player-5", name: "ユイ", alive: true, status: "alive" },
  { id: "player-6", name: "カイ", alive: true, status: "alive" },
];

export const sampleSetupOptions: GameSetupOptionsResponse = {
  player_count: { min: 5, max: 8, default: 6 },
  roles: [
    {
      id: "villager",
      name: "村人",
      faction: "villagers",
      abilities: [],
      description: "推理で村を守ります",
      difficulty: 1,
    },
    {
      id: "werewolf",
      name: "人狼",
      faction: "werewolves",
      abilities: ["werewolf_attack"],
      description: "夜に村を襲います",
      difficulty: 3,
    },
    {
      id: "seer",
      name: "占い師",
      faction: "villagers",
      abilities: ["seer_inspect"],
      description: "夜にひとりを調べます",
      difficulty: 2,
    },
    {
      id: "knight",
      name: "騎士",
      faction: "villagers",
      abilities: ["knight_guard"],
      description: "夜にひとりを守ります",
      difficulty: 2,
    },
  ],
  abilities: [
    {
      id: "seer_inspect",
      name: "占う",
      description: "夜にひとりを調べます",
      target_policy: "alive_other",
      difficulty: 2,
    },
  ],
  default_role_counts: { werewolf: 1, seer: 1, knight: 1, villager: 3 },
  default_rules: {
    day_speech_limit_per_player: 1,
    allow_self_vote: false,
    allow_vote_revision: false,
    allow_night_action_revision: false,
    enable_first_night_attack: true,
    enable_no_elimination_on_tie: true,
    enable_random_elimination_on_tie: false,
    allow_knight_self_guard: true,
    allow_knight_repeat_guard: true,
    allow_seer_self_inspect: false,
    allow_werewolf_friendly_fire: false,
    reveal_role_on_death: false,
  },
  default_scenario_id: "misty-village",
  default_setup_preset_id: "classic-six",
  default_narration_mode: "standard",
  default_agent_strategy_id: "stable_fast",
  scenarios: [
    { id: "misty-village", name: "霧の村", summary: "朝霧に包まれた静かな村" },
    { id: "moon-plaza", name: "月明かりの広場", summary: "月光が議論を照らす村" },
  ],
  setup_presets: [
    {
      id: "classic-six",
      name: "定番の6人村",
      scenario_id: "misty-village",
      role_counts: { werewolf: 1, seer: 1, knight: 1, villager: 3 },
    },
  ],
  characters: [
    {
      id: "aoi",
      name: "アオイ",
      age: 24,
      gender: "female",
      personality: "落ち着いた整理役",
      speaking_style: "短く丁寧",
      reasoning_style: "時系列重視",
      risk_tolerance: "medium",
    },
  ],
  agent_strategies: [
    { id: "stable_fast", name: "標準", description: "標準的な進行" },
  ],
};

export function sampleScreenSource(): GameScreenSource {
  return {
    state: {
      game_id: "sample-game",
      status: "running",
      phase: "day_discussion",
      day: 1,
      version: 2,
      seed: 17,
      scenario_id: "misty-village",
      scenario_name: "霧の村",
      narration_mode: "standard",
      players: samplePlayers,
      alive_player_ids: samplePlayers.map((player) => player.id),
      eliminated_player_ids: [],
      winner: null,
      summary: { public_note: "6人が生存しています" },
      created_at: sampleNow,
      updated_at: sampleNow,
    },
    timeline: {
      game_id: "sample-game",
      next_after: 2,
      items: [
        {
          sequence: 1,
          event_sequence: 1,
          version: 1,
          phase: "day_discussion",
          day: 1,
          actor_id: null,
          event_type: "game_created",
          narration: "霧の村に、静かな朝が訪れました。",
          payload: {},
          occurred_at: sampleNow,
        },
        {
          sequence: 2,
          event_sequence: 2,
          version: 2,
          phase: "day_discussion",
          day: 1,
          actor_id: "player-2",
          event_type: "speech",
          narration: "初日は発言の温度差を見たいです。",
          payload: { message: "初日は発言の温度差を見たいです。" },
          occurred_at: sampleNow,
        },
      ],
    },
    observation: {
      game_id: "sample-game",
      player_id: "player-1",
      observation: {
        phase: "day_discussion",
        day: 1,
        me: { id: "player-1", name: "アオイ", role: "seer", status: "alive" },
        known_roles: { "player-5": "villager" },
        available_actions: ["speech"],
        legal_targets: { vote: ["player-2"] },
      },
    },
    reveal: null,
  };
}
