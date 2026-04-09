# Remotion 렌더링 및 디자인 가이드

1. 렌더링 기본 원칙
- 모든 컴포넌트는 오직 텍스트 요소, 팝업(PopupElement), 시각 효과(FX)만을 렌더링한다.
- 영상의 배경은 철저히 투명하게(Alpha 채널 포함) 유지하여 Vrew에서 오버레이로 사용 가능해야 한다.

2. 시각 요소 배치 및 스타일링
- 팝업 이미지(PNG, JPG, JPEG)는 화면 중앙에 좌우 여백을 남기고 나타나야 한다.
- CSS의 `object-fit: contain` 속성을 사용하여 원본 이미지 비율을 유지한다.
- 시각 효과의 일관성을 위해 `PopupElement.tsx` 및 `src/components/fx/`에 정의된 컴포넌트를 최우선으로 재사용한다.

3. FX 컴포넌트 개발 규칙 (Custom 요청 대응)
- 새로운 효과를 만들 때는 반드시 `commonProps`(시간, 위치, 크기)를 상속받아 구현한다.
- 효과 고유의 파라미터는 Default 값을 지정하여 Props로 노출한다.