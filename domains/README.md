# domains

이 폴더는 `data-insight-kit`을 회사나 업무 도메인에 맞게 확장하기 위한
domain pack 영역입니다.

기본 배포 core는 특정 도메인을 포함하지 않습니다. 새 도메인이 필요하면
`template/`을 복사해 시작합니다.

```bash
cp -R domains/template domains/my-domain
```

## domain pack이 제공하는 것

- 도메인 용어와 사용자용 표현
- KPI 계산식, 분모, 단위, 비교 기준
- 도메인 전문가에게 물어볼 질문
- 대시보드 차트 흐름과 피해야 할 차트
- 요약 보고서와 심층 보고서의 구조
- 금지 표현과 근거 요구사항

domain pack은 자동 결론을 강제하지 않습니다. 에이전트가 사용자에게 더 좋은
질문을 하고, 도메인 전문가의 의도를 분석 계약에 반영하도록 돕는 보조 자료입니다.

## 폴더 구조

```text
domains/my-domain/
  domain.yaml
  terminology.md
  kpi-rules.md
  interview-questions.md
  dashboard-patterns.md
  report-rubric.md
  qa-rules.md
```

## 실행 연결

실행 시 pack 경로를 지정합니다.

```bash
DIK_DOMAIN_PACK=domains/my-domain/domain.yaml \
  DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

또는 run 입력 폴더에 참조 파일을 둡니다.

```bash
mkdir -p runs/my-run/input
printf 'domains/my-domain/domain.yaml\n' > runs/my-run/input/domain_pack_ref.txt
bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

wrapper는 다음 context 파일을 만듭니다.

```text
runs/my-run/input/domain_pack_context.md
runs/my-run/domain_pack_context.md
```

이 context는 이후 stage가 참고하지만, core 계약과 schema, QA를 대체하지 않습니다.
domain pack 기준이 결론이나 표현 수위를 바꾸면 중간 확인 단계에서 사용자가
승인해야 합니다.

## 인터뷰로 시작하기 (domain pack 없이)

domain pack이 아직 없어도 domain mode로 시작할 수 있습니다. wrapper 실행 시
`--domain-mode` 플래그를 붙이면 `input/run_context.json`에 스탬프가 기록되고,
이후 재실행에서 플래그를 생략해도 유지됩니다(수동 manifest 편집 불필요).

```bash
bash scripts/run_codex_pipeline.sh my-run --domain-mode
```

(기존 방식대로 run의 `manifest.json`에 `"domain_mode": true`를 표시해도
동일하게 인식됩니다.) domain mode가 켜지면 각 확인 단계 질문에 추가
확인 질문(행의 의미, 제외 기준, 지표 계산 기준 등)이 부족한 항목 우선으로
붙습니다. 답변이 쌓이면 파생 생성기로 도메인 확인 정보를 만듭니다.

```bash
python3 scripts/build_domain_intake.py my-run
# -> runs/my-run/input/domain_intake.json (generated_by + 근거 답변 id 기록)
```

- 수동으로 작성한 `domain_intake.json`이 이미 있으면 그 파일이 우선하고,
  인터뷰 답변은 남은 질문 목록으로만 보강됩니다.
- 도메인 기준 충족 상태(readiness)는 결정적으로 계산되며, 부족하면 도메인
  결론(추천·원인·성과 확정)이 QA에서 차단됩니다 — 인터뷰는 기회를 늘릴 뿐
  게이트를 약화하지 않습니다.

## run 지식의 승격 흐름

run에서 나온 반복 가능한 도메인 지식은 자동으로 domain pack이 되지 않습니다.

1. run 중 발견한 재사용 후보는 `runs/<run-id>/outputs/domain_pack_update_candidates.md`에 남깁니다.
   (용어, KPI 기준, 제외 규칙, 금지 표현 등 — 이 파일이 승격 후보의 단일 수집처)
2. 사람이 후보를 검토해 `domains/<domain>/` 파일에 직접 반영합니다.
3. run 진행 중 `domains/<domain>/` 자동 수정은 훅이 차단합니다 (영구 non-goal).

## 작성 체크리스트

- [ ] 도메인 용어를 사용자용 표현으로 풀어썼는가?
- [ ] KPI마다 계산식, 단위, 분모, 비교 기준이 있는가?
- [ ] 데이터에 없으면 말하면 안 되는 판단을 적었는가?
- [ ] 시작 질문, 데이터 확인 후 질문, 차트 구성 질문, 보고서 질문이 있는가?
- [ ] 추천 차트뿐 아니라 피해야 할 차트도 적었는가?
- [ ] 보고서 독자와 결론 수위 기준이 있는가?
- [ ] 금지 표현이 QA에서 확인 가능할 만큼 구체적인가?

## 배포 시 주의

domain pack에는 회사 내부 용어와 판단 기준이 들어갈 수 있습니다. 공개 배포본에는
민감한 domain pack을 포함하지 말고, 필요한 경우 `domains/template/`만 남깁니다.
