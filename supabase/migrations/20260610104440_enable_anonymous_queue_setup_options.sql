alter table public.definition_items
  drop constraint if exists definition_items_kind_check;

alter table public.definition_items
  add constraint definition_items_kind_check
  check (
    kind in (
      'ruleset',
      'role',
      'character',
      'scenario',
      'setup_preset',
      'narration_profile',
      'setup_options'
    )
  );

alter table private.game_snapshots
  drop column if exists manual_token_hashes;

insert into public.definition_items (
  id,
  owner_user_id,
  scope,
  kind,
  item_key,
  payload,
  active
)
values (
  '22222222-2222-4222-8222-222222222222',
  null,
  'system',
  'setup_options',
  'default',
  $json$
{
  "player_count": {"min": 5, "max": 8},
  "roles": [
    {
      "id": "villager",
      "name": "村人",
      "faction": "village",
      "abilities": [],
      "description": "特別な能力は持たず、発言と投票で人狼を探します。",
      "difficulty": 1
    },
    {
      "id": "werewolf",
      "name": "人狼",
      "faction": "werewolf",
      "abilities": ["night_attack", "pack_knowledge"],
      "description": "夜に襲撃し、昼は正体を隠して議論に参加します。",
      "difficulty": 2
    },
    {
      "id": "seer",
      "name": "占い師",
      "faction": "village",
      "abilities": ["inspect"],
      "description": "夜にひとりを調べ、推理の手がかりを得ます。",
      "difficulty": 2
    },
    {
      "id": "knight",
      "name": "騎士",
      "faction": "village",
      "abilities": ["guard"],
      "description": "夜にひとりを守り、襲撃から救えることがあります。",
      "difficulty": 2
    }
  ],
  "default_role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3},
  "default_rules": {
    "day_speech_limit_per_player": 1,
    "allow_self_vote": false,
    "allow_vote_revision": false,
    "allow_night_action_revision": false,
    "enable_first_night_attack": true,
    "enable_no_elimination_on_tie": true,
    "enable_random_elimination_on_tie": false,
    "allow_knight_self_guard": true,
    "allow_knight_repeat_guard": true,
    "allow_seer_self_inspect": false,
    "allow_werewolf_friendly_fire": false,
    "reveal_role_on_death": false
  },
  "default_scenario_id": "classic_village",
  "default_setup_preset_id": "standard_6",
  "default_narration_mode": "standard",
  "default_agent_strategy_id": "stable_fast",
  "abilities": [
    {
      "id": "night_attack",
      "name": "襲撃",
      "description": "夜にひとりを襲撃します。",
      "target_policy": "other_alive_non_pack",
      "difficulty": 2
    },
    {
      "id": "pack_knowledge",
      "name": "仲間認識",
      "description": "同じ人狼陣営の仲間を知っています。",
      "target_policy": "none",
      "difficulty": 2
    },
    {
      "id": "inspect",
      "name": "調査",
      "description": "夜にひとりの正体を調べます。",
      "target_policy": "other_alive",
      "difficulty": 2
    },
    {
      "id": "guard",
      "name": "護衛",
      "description": "夜にひとりを守ります。",
      "target_policy": "alive",
      "difficulty": 2
    }
  ],
  "scenarios": [
    {
      "id": "classic_village",
      "name": "古い村",
      "summary": "静かな村で、隠れた人狼を探します。",
      "recommended_setup_preset": "standard_6"
    },
    {
      "id": "sealed_lab",
      "name": "閉鎖研究所",
      "summary": "隔離された研究所で、異変の原因を追います。",
      "recommended_setup_preset": "standard_6"
    },
    {
      "id": "starship",
      "name": "宇宙船",
      "summary": "航行中の船内で、仲間に紛れた脅威を探します。",
      "recommended_setup_preset": "logic_6"
    }
  ],
  "setup_presets": [
    {
      "id": "standard_6",
      "name": "標準 6人",
      "scenario_id": "classic_village",
      "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3}
    },
    {
      "id": "logic_6",
      "name": "推理重視 6人",
      "scenario_id": "starship",
      "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3}
    }
  ],
  "characters": [
    {
      "id": "haruka",
      "name": "遥",
      "age": 28,
      "gender": "女性",
      "personality": "落ち着いて場を整理し、発言の食い違いを拾う。",
      "speaking_style": "短く丁寧に確認する。",
      "reasoning_style": "時系列と投票理由を重視する。",
      "risk_tolerance": "low"
    },
    {
      "id": "ren",
      "name": "蓮",
      "age": 31,
      "gender": "男性",
      "personality": "疑いを早めに出して議論を動かす。",
      "speaking_style": "率直で少し強めに話す。",
      "reasoning_style": "反応の速さと防御感を重視する。",
      "risk_tolerance": "high"
    },
    {
      "id": "aoi",
      "name": "葵",
      "age": 26,
      "gender": "指定なし",
      "personality": "周囲の発言をつなげて穏やかに推理する。",
      "speaking_style": "柔らかく問いかける。",
      "reasoning_style": "同意と便乗の差を重視する。",
      "risk_tolerance": "medium"
    },
    {
      "id": "minato",
      "name": "湊",
      "age": 34,
      "gender": "男性",
      "personality": "寡黙だが、要点だけを鋭く指摘する。",
      "speaking_style": "短文で断定を避ける。",
      "reasoning_style": "少ない情報から矛盾を探す。",
      "risk_tolerance": "medium"
    },
    {
      "id": "yui",
      "name": "結衣",
      "age": 29,
      "gender": "女性",
      "personality": "不安要素を丁寧に並べ、結論を急がない。",
      "speaking_style": "慎重で説明が細かい。",
      "reasoning_style": "発言量と視点漏れを重視する。",
      "risk_tolerance": "low"
    },
    {
      "id": "sora",
      "name": "空",
      "age": 24,
      "gender": "ノンバイナリー",
      "personality": "直感を言語化し、場の違和感を拾う。",
      "speaking_style": "自然体で少し感覚的に話す。",
      "reasoning_style": "発言の温度差と間を重視する。",
      "risk_tolerance": "medium"
    },
    {
      "id": "mei",
      "name": "芽衣",
      "age": 27,
      "gender": "女性",
      "personality": "相手の根拠を聞き出し、盤面を詰める。",
      "speaking_style": "質問を中心に話す。",
      "reasoning_style": "根拠の具体性を重視する。",
      "risk_tolerance": "medium"
    },
    {
      "id": "itsuki",
      "name": "樹",
      "age": 36,
      "gender": "男性",
      "personality": "早い仮説を置き、外れたらすぐ修正する。",
      "speaking_style": "テンポよく仮説を出す。",
      "reasoning_style": "初動と投票のずれを重視する。",
      "risk_tolerance": "high"
    },
    {
      "id": "riko",
      "name": "莉子",
      "age": 33,
      "gender": "女性",
      "personality": "他人の視点を整理し、対立軸を明確にする。",
      "speaking_style": "落ち着いた整理役として話す。",
      "reasoning_style": "対立している主張の差分を重視する。",
      "risk_tolerance": "low"
    },
    {
      "id": "kaito",
      "name": "海斗",
      "age": 30,
      "gender": "男性",
      "personality": "違和感を見つけるとすぐ確認する。",
      "speaking_style": "軽く切り込みながら話す。",
      "reasoning_style": "発言と投票の一貫性を重視する。",
      "risk_tolerance": "high"
    }
  ],
  "agent_strategies": [
    {
      "id": "stable_fast",
      "name": "Stable Fast",
      "description": "Fast and stable decisions with one model call, validation, one repair attempt, and deterministic fallback."
    },
    {
      "id": "role_basic",
      "name": "Role Basic",
      "description": "Adds short role-specific tactical hints while keeping the same validation and fallback behavior."
    },
    {
      "id": "target_ranker",
      "name": "Target Ranker",
      "description": "Ranks only legal targets before prompting so target-taking actions choose from safer candidates."
    }
  ]
}
$json$::jsonb,
  true
)
on conflict (id) do update set
  payload = excluded.payload,
  active = excluded.active,
  updated_at = timezone('utc', now());
