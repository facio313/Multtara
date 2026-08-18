# Multtara — Claude Gitflow Guide

> Claude (Anthropic) 에이전트 전용 브랜치 운영 규칙. 전체는 `AGENTS.md` 참고.

---

## 브랜치 구조

```
main                       ← 배포 기준 (직접 커밋 금지)
└── dev                    ← 통합 브랜치
    ├── anthropic          ← Claude 상주 브랜치 ✅
    │   └── anthropic-<feature>
    ├── cursor             ← Cursor 에이전트 (수정 금지)
    └── codex              ← Codex 에이전트 (수정 금지)
```

---

## Claude 작업 규칙

| 항목 | 규칙 |
|------|------|
| 상주 브랜치 / 워크트리 | `anthropic` / `worktrees/anthropic/` |
| 기능 브랜치 | `git checkout -b anthropic-<feature-name>` |
| 병합 방향 | `anthropic-<feature>` → `anthropic` → `dev` → `main` |
| `main` / `dev` 직접 커밋 | **금지** (사용자 명시 요청 시에만) |
| `cursor-*` / `codex-*` | **수정 금지** (읽기만) |
