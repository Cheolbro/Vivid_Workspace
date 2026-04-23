import os

file_path = r"c:\Youtube\Vivid_Workspace\fx_catalog.txt"

# Read existing content
with open(file_path, "rb") as f:
    content = f.read()

# Check where to append
if b"## Premium 3D" not in content:
    new_section = """
## Premium 3D 고퀄리티 이미지 에셋 (Batch 5)

| ID | type 값 | 설명 | 필수 specificProps |
|---|---|---|---|
| 058 | Generic3DAssetFX | 3D 하락/손실 차트 (레드) | assetName: "3d_loss_chart.png" |
| 059 | Generic3DAssetFX | 3D 상승/성장 차트 (그린) | assetName: "3d_growth_chart.png" |
| 060 | Generic3DAssetFX | 3D 초록색 상향 화살표 | assetName: "3d_green_arrow.png" |
| 061 | Generic3DAssetFX | 성장하는 수익 그래프 일러스트 | assetName: "profit_graph.png" |
| 062 | Generic3DAssetFX | 핵폭발 버섯구름 (위기, 파멸) | assetName: "mushroom_cloud.png" |
| 063 | Generic3DAssetFX | 3D 전함 (군사, 해군) | assetName: "battleship.png" |
| 064 | Generic3DAssetFX | 현대식 군함 (야간 조명) | assetName: "warship.png" |
| 065 | Generic3DAssetFX | 비행 중인 3D 비행기 | assetName: "airplane_3d.png" |
| 066 | Generic3DAssetFX | 여객기 일러스트 | assetName: "passenger_plane.png" |
| 067 | Generic3DAssetFX | 비행기 실루엣 아이콘 | assetName: "plane_silhouette.png" |
| 068 | Generic3DAssetFX | 택배 상자가 실린 배달 트럭 1 | assetName: "delivery_truck_1.png" |
| 069 | Generic3DAssetFX | 빨간색 도시 버스 모델 | assetName: "city_bus.png" |
| 070 | Generic3DAssetFX | 택배 상자가 실린 배달 트럭 2 | assetName: "delivery_truck_2.png" |
| 071 | Generic3DAssetFX | 달러 지폐 뭉치 | assetName: "dollar_pack.png" |
| 072 | Generic3DAssetFX | 3D 돈 가방 | assetName: "money_bag.png" |
| 073 | Generic3DAssetFX | 원형 미국 국기 아이콘 | assetName: "us_flag_circle.png" |
| 074 | Generic3DAssetFX | 원형 중국 국기 아이콘 | assetName: "china_flag_circle.png" |
| 075 | Generic3DAssetFX | 원형 한국 국기 아이콘 | assetName: "korea_flag_circle.png" |
| 076 | Generic3DAssetFX | K-손가락 하트 (사랑, 긍정) | assetName: "finger_heart.png" |
| 077 | Generic3DAssetFX | 3D 오일 드럼통 | assetName: "oil_barrel_3d.png" |
| 078 | Generic3DAssetFX | 가스 펌프(주유기) 아웃라인 | assetName: "gas_pump_outline.png" |
| 079 | Generic3DAssetFX | 가스 펌프(주유기) 클립아트 | assetName: "gas_pump_clipart.png" |
| 080 | Generic3DAssetFX | 연기가 나는 산업 공장 | assetName: "industry_plant.png" |
| 081 | Generic3DAssetFX | 크레인이 있는 건설 현장 | assetName: "construction_site.png" |
| 082 | Generic3DAssetFX | 초록색 회로 기판 위 마이크로칩 | assetName: "microchip_green.png" |
| 083 | Generic3DAssetFX | 고급 골드 마이크로칩 부품 | assetName: "advanced_microchip.png" |
"""
    with open(file_path, "wb") as f:
        f.write(content)
        f.write(new_section.encode('utf-8'))
    print("Added Batch 5 to catalog.")
else:
    print("Batch 5 already exists in catalog.")
