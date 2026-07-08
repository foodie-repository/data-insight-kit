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
