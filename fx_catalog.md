# FX 카탈로그 (fx_catalog.md)
> **[자동 관리 파일]** `src/components/fx/`에 컴포넌트 추가/삭제 시 즉시 업데이트 필수.
> 제미나이가 `remotion_plan.json` 작성 시 이 파일을 참조하여 `effect.type` 값을 결정합니다.

---

## 기본 내장 컴포넌트

| ID | type 값 | 파일 경로 | 설명 | 필수 Props |
|---|---|---|---|---|
| 001 | `Popup` | `src/components/PopupElement.tsx` | 이미지 팝업 (페이드인/아웃 + 스케일 애니메이션) | `src`, `startFrame`, `durationFrames` |

---

## Custom FX 컴포넌트 (동적 생성)

| ID | type 값 | 파일 경로 | 설명 | specificProps 기본값 |
|---|---|---|---|---|
| auto | `Custom` | `src/components/fx/MoneyRainFX.tsx` | 황금 동전 효과 | `particleCount`=30 / `color`=#FFD700 / `speed`=5.0 / `size`=24 | | | | |

---

## 사용 예시 (remotion_plan.json 작성 형식)

```json
{
  "effects": [
    {
      "id": "fx_001",
      "type": "Popup",
      "src": "image_1.jpeg",
      "startFrame": 90,
      "durationFrames": 60,
      "commonProps": { "width": "70%", "maxHeight": "70%" }
    },
    {
      "id": "fx_002",
      "type": "Custom",
      "description": "황금 동전이 위에서 아래로 떨어지는 파티클 효과",
      "startFrame": 150,
      "durationFrames": 90,
      "commonProps": { "x": "center", "y": "top" },
      "specificProps": {}
    }
  ]
}
```
