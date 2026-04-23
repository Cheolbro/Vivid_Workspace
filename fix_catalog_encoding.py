import os

file_path = r"c:\Youtube\Vivid_Workspace\fx_catalog.txt"

# Read existing good part (first 236 lines)
with open(file_path, "rb") as f:
    content = f.read()

# Try to find the last clean line. 
# We know the broken part starts after "direction 선택지: upward | downward | radial | leftward | rightward"
search_str = "direction 선택지: upward | downward | radial | leftward | rightward".encode('utf-8')
if search_str in content:
    clean_part = content.split(search_str)[0] + search_str + b"\n"
else:
    # Fallback: just take first 14000 bytes or so
    clean_part = content[:14207]

new_content_korean = """
## 신규 고급 텍스트 FX (Batch 1)

| ID | type 값 | 설명 | 필수 specificProps |
|---|---|---|---|
| 025 | SVGPathTypingFX | 펜으로 직접 쓰는 듯한 선 애니메이션 텍스트 | text, fontSize, color |
| 026 | SlidingBoxRevealFX | 박스가 지나가며 글자를 노출하는 뉴스 스타일 | text, fontSize, boxColor |
| 027 | SparkleTrailFX | 글자 주변에 화려한 파티클/스파클이 흩날리는 효과 | text, fontSize, sparkleColor |
| 028 | BouncingBallFX | 공이 단어 위를 통통 튀며 따라가는 리딩 가이드 | text, fontSize, ballColor |
| 029 | StaggeredFadeFX | 글자별 시차를 두고 부드럽게 페이드/블러 인 | text, fontSize, staggerDelay |
| 030 | VerticalMaskSlideFX | 마스크 영역 아래에서 위로 슥 올라오는 효과 | text, fontSize, maskHeight |
| 031 | BoldImpactSlideFX | 굵은 텍스트가 바닥에서 탄성 있게 튀어 오름 | text, fontSize, impactPower |
| 032 | RetroTerminalFX | 고전 해킹 터미널 스타일의 타이핑과 커서 | text, fontSize, color |
| 033 | NeonPulseGlowFX | 네온 사인이 숨을 쉬듯 맥동하는 화려한 효과 | text, fontSize, neonColor |

## Lottie 기반 특수 애니메이션 에셋 (Batch 2)

| ID | type 값 | 설명 | 필수 specificProps |
|---|---|---|---|
| 034 | MoneyLottieFX | 지폐와 동전이 모여있는 애니메이션 | scale |
| 035 | Coin3DLottieFX | 3D 스타일의 동전 회전 효과 | scale |
| 036 | MoneyStackLottieFX | 지폐 뭉치가 쌓여있는 정적/동적 애니메이션 | scale |
| 037 | MoneyRainLottieFX | 화면 가득 돈이 비처럼 내리는 화려한 효과 | scale |
| 038 | DollarLottieFX | 달러($) 기호가 강조되는 애니메이션 | scale |
| 039 | HandshakeLottieFX | 신뢰, 계약, 협력을 상징하는 악수 모션 | scale |
| 040 | CoinsDropLottieFX | 동전들이 위에서 아래로 떨어지는 효과 | scale |
| 041 | AnimatedLineGraphFX | 데이터가 실시간으로 우상향하는 선 그래프 | scale |
| 042 | LineGraphFX | 심플하고 깨끗한 선 그래프 애니메이션 | scale |
"""

with open(file_path, "wb") as f:
    f.write(clean_part)
    f.write(new_content_korean.encode('utf-8'))

print("Fixed encoding and restored content.")
