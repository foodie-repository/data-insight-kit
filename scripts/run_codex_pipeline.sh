#!/usr/bin/env bash
# data-insight-kit — Codex CLI 파이프라인 wrapper.
# 8개 stage와 4개 human checkpoint를 codex exec/결정적 gate로 순차 실행한다.
# stage 프롬프트는 agents/<stage>.md 재사용(Claude frontmatter 제거 — DRY).
# 단일 원천: docs/pipeline-contract.md.
#
# 사용법:
#   bash scripts/run_codex_pipeline.sh <run-id> [--dry-run] [--fresh] [--guided-intake] [--guided|--auto]
#   DIK_MODEL 환경변수로 모델 override (기본 gpt-5.5). 기존 VK_MODEL도 호환.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
usage: bash scripts/run_codex_pipeline.sh [run-id] [--dry-run] [--fresh] [--guided-intake] [--guided|--auto]

Options:
  --dry-run                 Print commands without running stages.
  --fresh                   Ignore cached stage artifacts.
  --guided-intake           Force the first intake pass through intake_draft.yaml.
  --force-intake-interview  Alias for --guided-intake.
  --guided                  Keep human checkpoints between explore/frame/analyze/visualize (default).
  --auto, --no-checkpoints  Skip mid-pipeline human checkpoints explicitly.
EOF
}

RUN_ID=""
DRY=0; FRESH=0; FORCE_GUIDED_INTAKE=0; CHECKPOINTS=1
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --fresh) FRESH=1 ;;
    --guided-intake|--force-intake-interview) FORCE_GUIDED_INTAKE=1 ;;
    --guided) CHECKPOINTS=1 ;;
    --auto|--no-checkpoints) CHECKPOINTS=0 ;;
    -h|--help) usage; exit 0 ;;
    --*) echo "알 수 없는 옵션: $a"; usage; exit 2 ;;
    *)
      if [ -n "$RUN_ID" ]; then
        echo "run-id는 하나만 지정할 수 있습니다: $RUN_ID, $a"; exit 2
      fi
      RUN_ID="$a"
      ;;
  esac
done
RUN_ID="${RUN_ID:-run-$(date +%Y%m%d-%H%M%S)}"
MODEL="${DIK_MODEL:-${VK_MODEL:-gpt-5.5}}"
RUN="runs/$RUN_ID"
mkdir -p "$RUN/input" "$RUN/intermediate" "$RUN/outputs"
USER_REQUEST="${DIK_USER_REQUEST:-${VK_USER_REQUEST:-}}"
if [ -z "$USER_REQUEST" ] && [ -f "$RUN/user_request.txt" ]; then
  USER_REQUEST="$(cat "$RUN/user_request.txt")"
fi

# 단계별 effort (model-tier-map.md)
effort_for() {
  case "$1" in
    intake|qa) echo "low" ;;
    connect|visualize|communicate) echo "medium" ;;
    explore|frame|analyze) echo "high" ;;
    *) echo "medium" ;;
  esac
}
# 단계별 산출물 (체크포인트용). 공백 없는 경로만 반환한다.
artifacts_for() {
  case "$1" in
    intake) echo "$RUN/manifest.json" ;;
    connect) echo "$RUN/outputs/01_profile.md" ;;
    explore) echo "$RUN/outputs/02_eda.md" ;;
    frame) echo "$RUN/outputs/03_frame.md" ;;
    analyze) echo "$RUN/outputs/04_analysis.md $RUN/outputs/chart_spec.json" ;;
    visualize) echo "$RUN/outputs/dashboard_data.json" ;;
    communicate) echo "$RUN/outputs/summary_report.md" ;;
    *) echo "" ;;
  esac
}

print_intake_question() {
  local qjson="$RUN/outputs/intake_questions.json"
  local qmd="$RUN/outputs/intake_questions.md"
  echo ""
  echo "⏸ intake 질문 필요 (run-id: $RUN_ID)"
  if [ -f "$qjson" ]; then
    python3 - "$qjson" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
decision_labels = {
    "decision_context": "분석 목적",
    "scope_focus": "분석 범위",
    "external_adapter_policy": "외부 보정 데이터 사용 여부",
    "report_contract": "보고서 깊이와 근거 범위",
}
print(f"질문 파일: {path}")
print("")
brief = data.get("user_analysis_brief") or {}
if brief:
    print("사용자용 분석 기획안")
    print(f"- 제목: {brief.get('plain_title', '')}")
    print(f"- 목적: {brief.get('analysis_goal', '')}")
    for label, key in (
        ("답할 질문", "answerable_questions"),
        ("이번 데이터로 볼 수 있는 것", "data_can_support"),
        ("이번 데이터만으로 판단하지 않을 것", "not_answerable"),
        ("중간 확인 시점", "checkpoint_plan"),
        ("실행 전 준비사항", "preflight_requirements"),
    ):
        values = brief.get(key) or []
        if values:
            print(f"- {label}:")
            for item in values[:5]:
                print(f"  - {item}")
    options = brief.get("analysis_options") or []
    if options:
        print("- 분석 방향 선택지:")
        for option in options[:3]:
            mark = " (추천)" if option.get("recommended") else ""
            print(f"  - {option.get('label', '')}{mark}: {option.get('description', '')}")
    approval_options = brief.get("approval_options") or []
    if approval_options:
        print("- 승인 선택지:")
        for option in approval_options[:4]:
            mark = " (추천)" if option.get("recommended") else ""
            print(f"  - {option.get('label', '')}{mark}: {option.get('description', '')}")
    if brief.get("approval_question"):
        print(f"- 승인 질문: {brief.get('approval_question')}")
    print("")
else:
    print("주의: user_analysis_brief가 없습니다. 사용자 검토용 기획안 없이 기술 질문만 표시될 수 있습니다.")
    print("")
print(f"현재 이해: {data.get('current_understanding', '')}")
print(f"막힌 결정: {data.get('blocked_decision', '')}")
recommended = data.get("recommended_option_id")
recommended_option = None
for option in data.get("options", []):
    if option.get("id") == recommended or option.get("recommended"):
        recommended_option = option
        break
if recommended_option:
    print(f"추천 답안: {recommended_option.get('label', recommended)} — {recommended_option.get('description', '')}")
state = data.get("interview_state") or {}
if state:
    print("")
    print(f"질문 진행: {state.get('question_index', '?')}/{state.get('max_questions', '?')}")
    answered = state.get("answered_decisions") or {}
    remaining = state.get("remaining_decisions") or []
    if answered:
        print("이미 답한 결정:")
        for key, value in answered.items():
            print(f"- {decision_labels.get(key, key)}: {value}")
    if remaining:
        print("남은 결정:")
        for item in remaining:
            print(f"- {decision_labels.get(item, item)}")
print("")
print(f"질문: {data.get('question', '')}")
print("선택지:")
for option in data.get("options", []):
    mark = " (추천)" if option.get("id") == recommended or option.get("recommended") else ""
    print(f"- {option.get('label')}{mark}")
    print(f"  {option.get('description')}")
if data.get("allow_free_text"):
    print("- 직접 입력 가능")
instructions = data.get("response_instructions") or {}
if instructions:
    print("")
    print("기술 정보:")
    mode = instructions.get("mode")
    if mode:
        print(f"응답 모드: {mode}")
    print(f"답변 반영 위치: {instructions.get('write_to', '')}")
    if instructions.get("finalize_to"):
        print(f"최종 intake 위치: {instructions.get('finalize_to')}")
    if instructions.get("apply_command"):
        print(f"답변 누적 명령: {instructions.get('apply_command')}")
    print(f"재실행 명령: {instructions.get('resume_command', '')}")
PY
  elif [ -f "$qmd" ]; then
    echo "질문 파일: $qmd"
    echo ""
    sed -n '1,220p' "$qmd"
  else
    echo "manifest가 사용자 질문 필요 상태를 가리키지만 intake 질문 파일이 없습니다."
  fi
  echo ""
  echo "중단: 사용자 답변을 안내된 위치에 반영한 뒤 같은 명령으로 재실행하세요."
}

manifest_intake_blocked() {
  local manifest="$1"
  [ -f "$manifest" ] || { echo "0"; return 0; }
  python3 - "$manifest" <<'PY'
import json
import pathlib
import sys

try:
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit

stages = data.get("stages") or []
intake = data.get("intake") or {}
qa = data.get("qa") or {}
blocked = any(s.get("name") == "intake" and s.get("status") == "blocked_for_user_question" for s in stages)
blocked = blocked or (qa.get("block") is True and (intake.get("interview") or {}).get("needed") is True)
print("1" if blocked else "0")
PY
}

prepare_intake_resume() {
  local qjson="$RUN/outputs/intake_questions.json"
  local qmd="$RUN/outputs/intake_questions.md"
  local manifest="$RUN/manifest.json"
  local has_intake=0

  for path in "$RUN/intake_draft.yaml" "$RUN/input/intake_draft.yaml" "$RUN/intake.yaml" "$RUN/input/intake.yaml"; do
    [ -f "$path" ] && has_intake=1
  done

  if [ "$has_intake" -eq 1 ]; then
    local blocked="0"
    blocked="$(manifest_intake_blocked "$manifest")"
    if [ -f "$qjson" ] || [ -f "$qmd" ] || [ "$blocked" = "1" ]; then
      rm -f "$qjson" "$qmd"
      rm -f "$manifest"
    fi
  fi
}

check_intake_question() {
  local qjson="$RUN/outputs/intake_questions.json"
  local qmd="$RUN/outputs/intake_questions.md"
  local manifest="$RUN/manifest.json"
  if [ -f "$qjson" ] || [ -f "$qmd" ]; then
    local files=()
    [ -f "$qjson" ] && files+=("$qjson")
    [ -f "$qmd" ] && files+=("$qmd")
    python3 scripts/validate_user_facing_text.py "${files[@]}"
    print_intake_question
    exit 3
  fi
  if [ -f "$manifest" ]; then
    local blocked
    blocked="$(manifest_intake_blocked "$manifest")"
    if [ "$blocked" = "1" ]; then
      local files=()
      [ -f "$qjson" ] && files+=("$qjson")
      [ -f "$qmd" ] && files+=("$qmd")
      if [ "${#files[@]}" -gt 0 ]; then
        python3 scripts/validate_user_facing_text.py "${files[@]}"
      fi
      print_intake_question
      exit 3
    fi
  fi
}

final_intake_has_guided_trace() {
  python3 - "$RUN/intake.yaml" "$RUN/input/intake.yaml" <<'PY'
import pathlib
import re
import sys

guided = False
for raw in sys.argv[1:]:
    path = pathlib.Path(raw)
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    guided = guided or bool(re.search(r"finalized_by:\s*(guided_intake|wrapper_guided_intake|ask_user_question|user_popup)\b", text))
    guided = guided or '"finalized_by": "guided_intake"' in text
    guided = guided or '"finalized_by": "ask_user_question"' in text
    guided = guided or '"finalized_by": "user_popup"' in text
print("1" if guided else "0")
PY
}

seed_guided_intake_question() {
  local qjson="$RUN/outputs/intake_questions.json"
  local qmd="$RUN/outputs/intake_questions.md"
  local manifest="$RUN/manifest.json"
  local has_draft=0
  local has_final=0

  [ "$FORCE_GUIDED_INTAKE" -eq 1 ] || return 0
  if [ "$DRY" -eq 1 ]; then
    for path in "$RUN/intake_draft.yaml" "$RUN/input/intake_draft.yaml"; do [ -f "$path" ] && has_draft=1; done
    for path in "$RUN/intake.yaml" "$RUN/input/intake.yaml"; do [ -f "$path" ] && has_final=1; done
    if [ "$has_draft" -eq 1 ]; then
      echo "    guided-intake preflight: intake_draft.yaml 기반으로 intake 재개 예정"
    elif [ "$has_final" -eq 1 ]; then
      if [ "$(final_intake_has_guided_trace)" = "1" ]; then
        echo "    guided-intake preflight: guided trace가 있는 intake.yaml 사용 예정"
      else
        echo "    guided-intake preflight: intake.yaml 에 guided finalization trace가 없어 exit 2 예정"
        exit 0
      fi
    else
      echo "    guided-intake preflight: intake_questions.json 생성 후 exit 3 예정"
      exit 0
    fi
    return 0
  fi
  for path in "$RUN/intake_draft.yaml" "$RUN/input/intake_draft.yaml"; do [ -f "$path" ] && has_draft=1; done
  for path in "$RUN/intake.yaml" "$RUN/input/intake.yaml"; do [ -f "$path" ] && has_final=1; done
  if [ "$has_draft" -eq 1 ]; then
    return 0
  fi
  if [ "$has_final" -eq 1 ]; then
    if [ "$(final_intake_has_guided_trace)" = "1" ]; then
      return 0
    fi
    echo "✗ --guided-intake 요청됨: 기존 intake.yaml 에 guided finalization trace가 없습니다."
    echo "  이 run에서 질문형 intake를 검증하려면 답변을 runs/$RUN_ID/intake_draft.yaml 또는 runs/$RUN_ID/input/intake_draft.yaml 에 누적하거나,"
    echo "  최종 intake에 finalization.finalized_by: guided_intake 를 명시하세요."
    exit 2
  fi
  if [ -f "$qjson" ] || [ -f "$qmd" ]; then
    local files=()
    [ -f "$qjson" ] && files+=("$qjson")
    [ -f "$qmd" ] && files+=("$qmd")
    python3 scripts/validate_user_facing_text.py "${files[@]}"
    print_intake_question
    exit 3
  fi

  python3 - "$RUN_ID" "$RUN" "$USER_REQUEST" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

run_id, run, user_request = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3].strip()
outputs = run / "outputs"
outputs.mkdir(parents=True, exist_ok=True)

external_context_terms = ("외부 데이터", "외부 보정", "보정 데이터", "추가 데이터", "external adapter", "external context")
needs_adapter_policy = any(term.lower() in user_request.lower() for term in external_context_terms)
remaining_decisions = ["scope_focus", "report_contract"]
if needs_adapter_policy:
    remaining_decisions.insert(1, "external_adapter_policy")
is_api_request = any(term.lower() in user_request.lower() for term in ("api", "data.go.kr", "공공데이터", "열린데이터"))

understanding = (
    f"사용자는 '{user_request}' 요청으로 데이터 분석 보고서와 대시보드를 만들고 싶다."
    if user_request
    else "사용자는 입력 데이터로 분석 보고서와 대시보드를 만들고 싶다."
)
user_analysis_brief = {
    "plain_title": "이번 분석으로 무엇을 판단할지 먼저 정합니다",
    "analysis_goal": "데이터를 수집하거나 분석하기 전에, 결과물로 어떤 판단을 돕고 싶은지 확인합니다.",
    "answerable_questions": [
        "분석 대상과 범위는 무엇인가요?",
        "어떤 세그먼트나 기간을 비교해야 하나요?",
        "현황·변화·차이·예외 중 무엇을 우선 확인해야 하나요?",
        "결과를 보고 사용자가 다음에 무엇을 결정해야 하나요?",
    ],
    "data_can_support": [
        "입력 데이터에 들어 있는 범위, 기간, 컬럼으로 직접 계산 가능한 지표",
        "데이터 탐색 후 확인되는 세그먼트, 분포, 변화, 관계, 예외",
    ],
    "not_answerable": [
        "데이터에 없는 수요, 비용, 성과, 원인, 미래 결과를 확정하는 판단",
        "사용자 목적과 성공 기준이 정해지기 전의 최종 차트 구성",
    ],
    "analysis_options": [
        {
            "label": "후보·우선순위 판단",
            "description": "여러 대상이나 세그먼트를 비교해 우선순위를 정합니다.",
            "recommended": True,
        },
        {
            "label": "현황·리스크 진단",
            "description": "성과, 집중도, 이상치, 위험 요인을 찾아 개선 포인트를 봅니다.",
        },
        {
            "label": "데이터 탐색",
            "description": "명확한 결론보다 데이터 구조와 주요 세그먼트를 먼저 발견합니다.",
        },
    ],
    "checkpoint_plan": [
        "데이터 샘플과 품질 요약을 보여주고 범위가 맞는지 확인합니다.",
        "핵심 지표와 분석 방향 선택지를 제안하고 다시 확인합니다.",
        "대시보드 구성안을 승인받은 뒤 화면을 만듭니다.",
        "최종 보고서의 독자, 흐름, 문체, 결론 수위를 확인한 뒤 작성합니다.",
    ],
    "preflight_requirements": [
        "원천 파일이나 API 키처럼 데이터 접근에 필요한 준비사항이 있는지 먼저 확인합니다.",
        "데이터가 없거나 인증이 막히면 대체 데이터를 만들지 않고 수집 문제로 멈춥니다.",
    ] if is_api_request else [
        "입력 파일, 원격 스냅샷, API 접근 권한처럼 데이터 접근에 필요한 준비사항을 확인합니다.",
        "데이터가 없거나 접근이 막히면 대체 데이터를 만들지 않고 원천 문제로 멈춥니다.",
    ],
    "approval_options": [
        {
            "label": "추천 방향으로 진행",
            "description": "후보·우선순위 판단을 기준으로 데이터 확인 단계부터 시작합니다.",
            "recommended": True,
        },
        {
            "label": "범위나 대상을 바꾸기",
            "description": "분석 대상, 기간, 지역, 고객군, 제품군 같은 범위를 먼저 조정합니다.",
        },
        {
            "label": "목적을 다시 정하기",
            "description": "현황 진단, 위험 점검, 단순 탐색 중 다른 방향을 고릅니다.",
        },
    ],
    "approval_question": "먼저 이번 분석 결과로 무엇을 판단할지 선택해도 될까요?",
}
decision_options = [
    {
        "id": "decision_support",
        "label": "후보·우선순위 판단",
        "description": "분석 대상이나 세그먼트를 비교해 우선순위를 정한다.",
        "recommended": True,
        "maps_to": {"analysis_mode": "candidate_prioritization"},
    },
    {
        "id": "diagnosis",
        "label": "현황·리스크 진단",
        "description": "성과, 집중도, 이상치, 위험 요인을 찾아 개선 포인트를 정한다.",
        "maps_to": {"analysis_mode": "status_diagnosis"},
    },
    {
        "id": "exploration",
        "label": "데이터 탐색",
        "description": "명확한 의사결정보다 데이터의 구조와 주요 세그먼트를 먼저 발견한다.",
        "maps_to": {"analysis_mode": "segment_discovery"},
    },
]
decision_question = "이번 분석 결과로 무엇을 판단하려고 하시나요?"
question = {
    "schema_version": "data-insight-kit.intake_question.v1",
    "run_id": run_id,
    "status": "blocked_for_user_question",
    "question_id": "decision_context",
    "header": "분석 목적",
    "user_analysis_brief": user_analysis_brief,
    "current_understanding": understanding,
    "blocked_decision": "심층 분석을 시작하기 전에 이 결과로 내릴 판단 또는 다음 행동을 확정해야 한다.",
    "recommended_option_id": "decision_support",
    "question": decision_question,
    "options": decision_options,
    "allow_free_text": True,
    "interview_state": {
        "question_index": 1,
        "max_questions": 3,
        "answered_decisions": {},
        "remaining_decisions": remaining_decisions,
        "can_finalize_after_answer": False,
        "finalization_rule": "답변은 intake_draft.yaml에 누적하고, 남은 결정이 기본값으로 안전하게 채워질 때만 intake.yaml을 확정한다.",
    },
    "response_instructions": {
        "mode": "draft",
        "write_to": f"runs/{run_id}/intake_draft.yaml",
        "finalize_to": f"runs/{run_id}/intake.yaml",
        "apply_command": f"python3 scripts/apply_intake_answer.py {run_id} --option <option-id>",
        "resume_command": f"bash scripts/run_codex_pipeline.sh {run_id} --guided-intake",
    },
}
recommended_option = next(
    (opt for opt in question["options"] if opt.get("id") == question["recommended_option_id"]),
    None,
)
(outputs / "intake_questions.json").write_text(json.dumps(question, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(outputs / "intake_questions.md").write_text(
    "\n".join([
        "# intake 질문 필요",
        "",
        "## 사용자용 분석 기획안",
        "",
        f"### {user_analysis_brief['plain_title']}",
        "",
        user_analysis_brief["analysis_goal"],
        "",
        "답할 질문:",
        *[f"- {item}" for item in user_analysis_brief["answerable_questions"]],
        "",
        "이번 데이터로 볼 수 있는 것:",
        *[f"- {item}" for item in user_analysis_brief["data_can_support"]],
        "",
        "이번 데이터만으로 판단하지 않을 것:",
        *[f"- {item}" for item in user_analysis_brief["not_answerable"]],
        "",
        "추천 분석 방향:",
        *[
            f"- {opt['label']}: {opt['description']}" + (" (추천)" if opt.get("recommended") else "")
            for opt in user_analysis_brief["analysis_options"]
        ],
        "",
        "중간 확인 시점:",
        *[f"- {item}" for item in user_analysis_brief["checkpoint_plan"]],
        "",
        "실행 전 준비사항:",
        *[f"- {item}" for item in user_analysis_brief["preflight_requirements"]],
        "",
        "승인 선택지:",
        *[
            f"- {opt['label']}: {opt['description']}" + (" (추천)" if opt.get("recommended") else "")
            for opt in user_analysis_brief["approval_options"]
        ],
        "",
        f"승인 질문: {user_analysis_brief['approval_question']}",
        "",
        "## 채팅 질문",
        "",
        f"현재 이해: {question['current_understanding']}",
        f"막힌 결정: {question['blocked_decision']}",
        "추천 답안: "
        + (
            f"{recommended_option['label']} — {recommended_option['description']}"
            if recommended_option
            else ""
        ),
        f"질문: {question['question']}",
        "",
        "선택지:",
        *[f"- {opt['label']} — {opt['description']}" for opt in question["options"]],
        "- 직접 입력 가능",
        "",
        "## 기술 부록",
        "",
        "선택지 ID:",
        *[f"- {opt['id']}: {opt['label']}" for opt in question["options"]],
        "",
        f"답변 반영 위치: runs/{run_id}/intake_draft.yaml",
        f"답변 누적 명령: python3 scripts/apply_intake_answer.py {run_id} --option <option-id>",
        f"재실행 명령: bash scripts/run_codex_pipeline.sh {run_id} --guided-intake",
        "",
    ]),
    encoding="utf-8",
)
manifest = {
    "run_id": run_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "intake": {
        "mode": "exploratory",
        "objective": user_request or "guided intake answer pending",
        "decision_context": "",
        "analysis_mode": "custom",
        "known_questions": [],
        "success_criteria": [],
        "exclusions": [],
        "constraints": [],
        "open_questions": ["decision_context", "scope_focus", "report_contract"],
        "interview": {
            "needed": True,
            "style": "ask_user_question + deep_interview",
            "question_count": 0,
            "unresolved": ["decision_context", "scope_focus", "report_contract"],
        },
        "report": {"depth": "standard", "audience": "mixed", "evidence_scope": "data_only"},
    },
    "stages": [
        {
            "name": "intake",
            "status": "blocked_for_user_question",
            "outputs": [
                f"runs/{run_id}/outputs/intake_questions.json",
                f"runs/{run_id}/outputs/intake_questions.md",
            ],
            "notes": ["--guided-intake preflight generated the first AskUserQuestion handoff before final intake.yaml."],
        }
    ],
}
(run / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  python3 scripts/validate_user_facing_text.py "$qjson" "$qmd"
  print_intake_question
  exit 3
}

prepare_external_adapter_plan() {
  if [ "$DRY" -eq 1 ]; then
    echo "    external-adapter preflight: intake.external_adapters 정책을 external_adapter_plan.json 으로 준비 예정"
    return 0
  fi
  set +e
  python3 scripts/prepare_external_adapter_plan.py "$RUN_ID" --user-request "$USER_REQUEST" --require-if-relevant
  local status=$?
  set -e
  if [ "$status" -eq 3 ]; then
    local qjson="$RUN/outputs/intake_questions.json"
    local qmd="$RUN/outputs/intake_questions.md"
    local files=()
    [ -f "$qjson" ] && files+=("$qjson")
    [ -f "$qmd" ] && files+=("$qmd")
    if [ "${#files[@]}" -gt 0 ]; then
      python3 scripts/validate_user_facing_text.py "${files[@]}"
    fi
    print_intake_question
    exit 3
  fi
  if [ "$status" -ne 0 ]; then
    echo "✗ external adapter plan 준비 실패(status=$status)"
    exit "$status"
  fi
}

prepare_domain_pack_context() {
  if [ "$DRY" -eq 1 ]; then
    echo "    domain-pack preflight: DIK_DOMAIN_PACK 또는 intake domain pack 선택 시 context 준비 예정"
    return 0
  fi
  python3 scripts/prepare_domain_pack_context.py "$RUN_ID"
}

request_has_primary_api() {
  python3 scripts/prepare_primary_api_source.py "$RUN_ID" --user-request "$USER_REQUEST" --check-only
}

prepare_primary_api_source() {
  local has_api
  has_api="$(request_has_primary_api)"
  [ "$has_api" = "1" ] || return 0
  if [ "$DRY" -eq 1 ]; then
    python3 scripts/prepare_primary_api_source.py "$RUN_ID" --user-request "$USER_REQUEST" --dry-run >/dev/null
    echo "    primary-api preflight: API URL 요청 감지, input/source_api_manifest.json 생성 예정"
    return 0
  fi
  python3 scripts/prepare_primary_api_source.py "$RUN_ID" --user-request "$USER_REQUEST"
}

prepare_primary_api_source

# 소스 확인
if [ ! -f connectors/.env ] && [ -z "$(ls -A "$RUN/input" 2>/dev/null)" ]; then
  if [ "$(request_has_primary_api)" = "1" ]; then
    if [ "$DRY" -eq 1 ]; then
      echo "    source preflight: API URL 요청이므로 source_api_manifest.json 생성 후 connect 예정"
    else
      echo "소스 없음: API URL은 감지했지만 source_api_manifest.json을 만들지 못했습니다."; exit 2
    fi
  else
    echo "소스 없음: $RUN/input/ 에 CSV·Parquet·Excel·JSON, 축약 스냅샷 또는 source_api_manifest.json을 두세요. DuckDB 사용자는 connectors/.env(DIK_DUCKDB_PATH)를 설정하세요."; exit 2
  fi
fi

run_stage() {
  local stage="$1" effort; effort="$(effort_for "$stage")"
  local arts; arts="$(artifacts_for "$stage")"
  if [ "$FRESH" -eq 0 ] && [ -n "$arts" ]; then
    local all_cached=1
    for art in $arts; do
      [ -f "$art" ] || all_cached=0
    done
    if [ "$all_cached" -eq 1 ]; then
      echo "✅ $stage (cached: $arts)"; return 0
    fi
  fi
  # agents/<stage>.md 본문만 추출 (상단 --- frontmatter --- 제거)
  local body; body="$(awk 'BEGIN{fm=0} /^---[[:space:]]*$/{fm++; next} fm>=2{print}' "agents/$stage.md")"
  local request_block=""
  if [ -n "$USER_REQUEST" ]; then
    request_block="
[사용자 원 발화]
$USER_REQUEST
"
  fi
  local guided_block=""
  if [ "$FORCE_GUIDED_INTAKE" -eq 1 ]; then
    guided_block="
[guided intake 실행 옵션]
--guided-intake가 활성화되어 있다. 이 run은 질문형 intake UX 검증 대상이다.
- 사용자 답변은 먼저 $RUN/intake_draft.yaml 에 누적된 것으로 본다.
- 충분한 답변이 모였을 때만 $RUN/intake.yaml 을 확정한다.
- 최종 intake.yaml 에는 interview.question_count >= 1 과 finalization.finalized_by: guided_intake 를 남긴다.
- 외부 context가 결론 품질을 크게 바꾸거나 사용자가 외부 보정 데이터를 명시한 요청이면 final intake 전에 external_adapter_policy 질문을 검토한다. 질문을 만들면 question_kind=external_adapter_policy, maps_to.external_adapters, adapter_selection.registry_ref 를 포함한다.
- 아직 핵심 결정이 부족하면 outputs/intake_questions.json/md 를 다시 만들고 blocked_for_user_question 상태로 중단한다.
"
  fi
  local adapter_policy_block=""
  if [ "$stage" != "intake" ] && [ -f "$RUN/input/external_adapter_plan.json" ]; then
    adapter_policy_block="$(python3 scripts/prepare_external_adapter_plan.py "$RUN_ID" --print-prompt-block || true)"
    adapter_policy_block="
$adapter_policy_block
"
  fi
  local primary_api_block=""
  if [ "$stage" != "intake" ] && [ -f "$RUN/input/source_api_manifest.json" ]; then
    primary_api_block="$(python3 scripts/prepare_primary_api_source.py "$RUN_ID" --print-prompt-block || true)"
    primary_api_block="
$primary_api_block
"
  fi
  local domain_pack_block=""
  if [ -f "$RUN/input/domain_pack_context.md" ]; then
    domain_pack_block="$(python3 scripts/prepare_domain_pack_context.py "$RUN_ID" --print-prompt-block || true)"
    domain_pack_block="
$domain_pack_block
"
  fi
  local checkpoint_block=""
  if [ "$stage" != "intake" ] && [ -f "$RUN/input/checkpoint_answers.json" ]; then
    checkpoint_block="
[사용자 중간 체크포인트 답변]
$RUN/input/checkpoint_answers.json 을 반드시 읽고, 승인된 checkpoint 답변의 지시와 free-text를 다음 산출물에 반영하라. continue_pipeline=false 로 남은 최신 답변이 있으면 새 산출물을 만들기 전에 그 수정 요구를 해결해야 한다.
"
  fi
  local prompt="run-id: $RUN_ID
산출 경로: $RUN/
단일 원천 docs/pipeline-contract.md 의 [$stage] 계약을 준수하라.
DB 접근은 connectors/source.py 경유(read-only). 쓰기는 $RUN/ 안에만.
$request_block
$guided_block
$primary_api_block
$adapter_policy_block
$domain_pack_block
$checkpoint_block

[단계 사양: agents/$stage.md]
$body"
  echo "▶ $stage (effort=$effort, model=$MODEL)"
  if [ "$DRY" -eq 1 ]; then
    echo "    codex exec -C \"$ROOT\" -m $MODEL -c 'model_reasoning_effort=\"$effort\"' --sandbox workspace-write <prompt:$stage>"
    return 0
  fi
  codex exec -C "$ROOT" -m "$MODEL" -c "model_reasoning_effort=\"$effort\"" \
    --sandbox workspace-write "$prompt"
  if [ -n "$arts" ]; then
    for art in $arts; do
      if [ ! -f "$art" ]; then echo "✗ $stage 산출물 없음($art) — 중단"; exit 1; fi
    done
  fi
}

run_checkpoint() {
  local checkpoint="$1"
  if [ "$CHECKPOINTS" -eq 0 ]; then
    echo "⏭ checkpoint:$checkpoint (--auto/--no-checkpoints)"
    return 0
  fi
  echo "▶ checkpoint:$checkpoint (사용자 확인 게이트)"
  if [ "$DRY" -eq 1 ]; then
    python3 scripts/checkpoint_gate.py "$RUN_ID" "$checkpoint" --dry-run
    return 0
  fi
  set +e
  python3 scripts/checkpoint_gate.py "$RUN_ID" "$checkpoint"
  local status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    return 0
  fi
  if [ "$status" -eq 3 ]; then
    local base=""
    case "$checkpoint" in
      data_profile) base="01_data_profile_question" ;;
      analysis_strategy) base="02_analysis_strategy_question" ;;
      dashboard_storyboard) base="03_dashboard_storyboard_question" ;;
      report_outline) base="04_report_outline_question" ;;
    esac
    if [ -n "$base" ]; then
      local files=()
      [ -f "$RUN/outputs/checkpoints/$base.json" ] && files+=("$RUN/outputs/checkpoints/$base.json")
      [ -f "$RUN/outputs/checkpoints/$base.md" ] && files+=("$RUN/outputs/checkpoints/$base.md")
      if [ "${#files[@]}" -gt 0 ]; then
        python3 scripts/validate_user_facing_text.py "${files[@]}"
      fi
    fi
    exit 3
  fi
  if [ "$status" -eq 4 ]; then
    echo "✗ CHECKPOINT REVISION REQUIRED — 사용자 수정 요청이 반영되기 전까지 다음 단계로 진행하지 않습니다."
    exit 4
  fi
  echo "✗ checkpoint 실패(status=$status): $checkpoint"
  exit "$status"
}

# 0~5단계 (intake~visualize)
prepare_intake_resume
prepare_domain_pack_context
seed_guided_intake_question

command -v codex >/dev/null 2>&1 || { echo "codex CLI 없음 — /codex:setup 또는 설치 필요"; exit 2; }

run_stage intake
check_intake_question
prepare_external_adapter_plan
prepare_domain_pack_context
run_stage connect
run_stage explore
run_checkpoint data_profile
run_stage frame
run_checkpoint analysis_strategy
run_stage analyze
run_checkpoint dashboard_storyboard
run_stage visualize

# 6단계 qa = 결정적 게이트 (validate.py)
echo "▶ qa (결정적 게이트)"
if [ "$DRY" -eq 1 ]; then
  echo "    python qa/validate.py $RUN/outputs/dashboard_data.json --chart-spec $RUN/outputs/chart_spec.json"
else
  if ! python3 qa/validate.py "$RUN/outputs/dashboard_data.json" --chart-spec "$RUN/outputs/chart_spec.json"; then
    echo "✗ QA BLOCK — 출고 차단. visualize 재검토 후 재실행(계약: 기계적 결함 1회 자동수정)."; exit 1
  fi
fi

# H4 보고서 구성 확인. 대시보드 QA를 통과한 실제 산출물을 보고 난 뒤
# communicate가 어떤 독자·깊이·문체로 보고서를 작성할지 확인한다.
run_checkpoint report_outline

# 7단계 communicate
run_stage communicate

# communicate 이후 보고서 깊이 게이트. 렌더는 6단계에서 이미 확인했으므로 정적 보고서 검사만 수행.
echo "▶ qa-post (보고서 깊이 게이트)"
if [ "$DRY" -eq 1 ]; then
  echo "    python qa/validate.py $RUN/outputs/dashboard_data.json --chart-spec $RUN/outputs/chart_spec.json --no-render --post-communicate"
else
  if ! python3 qa/validate.py "$RUN/outputs/dashboard_data.json" --chart-spec "$RUN/outputs/chart_spec.json" --no-render --post-communicate; then
    echo "✗ QA POST BLOCK — 보고서 깊이/근거 계약 미달. communicate 재검토 후 재실행."; exit 1
  fi
fi

echo ""
echo "✅ 파이프라인 완료 (run-id: $RUN_ID)"
for f in 01_profile.md 02_eda.md 03_frame.md 04_analysis.md chart_spec.json dashboard.html summary_report.md deep_report.md external_context.md; do
  [ -f "$RUN/outputs/$f" ] && echo "  📄 $RUN/outputs/$f"
done
exit 0
