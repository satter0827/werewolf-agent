import type { GameSetupOptionsResponse, PublicPlayerState } from "../gameClient/wireTypes";

export const demoNow = "2026-06-04T00:00:00Z";

export const demoPlayers: PublicPlayerState[] = [
  { id: "player-1", name: "アオイ", alive: true, status: "alive" },
  { id: "player-2", name: "レン", alive: true, status: "alive" },
  { id: "player-3", name: "ミナ", alive: true, status: "alive" },
  { id: "player-4", name: "ソウ", alive: true, status: "alive" },
  { id: "player-5", name: "ユイ", alive: true, status: "alive" },
  { id: "player-6", name: "カイ", alive: true, status: "alive" },
];

export const demoRoleAssignments: Record<string, string> = {
  "player-1": "seer",
  "player-2": "werewolf",
  "player-3": "villager",
  "player-4": "villager",
  "player-5": "villager",
  "player-6": "knight",
};

export const demoSetupOptions: GameSetupOptionsResponse = {
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
    { id: "misty-village", name: "霧の村", description: "朝霧に包まれた静かな村" },
    { id: "moon-plaza", name: "月明かりの広場", description: "月光が議論を照らす村" },
    { id: "old-inn", name: "古い宿場", description: "旅人の噂が交差する宿場町" },
  ],
  setup_presets: [
    {
      id: "classic-six",
      name: "定番の6人村",
      description: "初めてでも遊びやすい配役",
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
};
