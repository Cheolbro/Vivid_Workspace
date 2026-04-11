import os
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가하여 utils 패키지를 로드할 수 있게 함
sys.path.append(str(Path(__file__).parent))

try:
    from utils.google_auth import configure_genai
    import google.generativeai as genai
except ImportError as e:
    print(f"Error: {e}")
    print("필요한 라이브러리를 설치하세요: pip install google-auth-oauthlib google-auth-httplib2 google-auth google-generativeai")
    sys.exit(1)

def test_auth():
    print("--- Google OAuth2 인증 테스트 ---")
    try:
        # client_secret.json이 있는지 확인
        if not os.path.exists("client_secret.json"):
            print("Error: 'client_secret.json' 파일이 프로젝트 루트에 없습니다.")
            return

        print("인증을 진행합니다. 브라우저가 열리면 승인해주세요...")
        # 이 과정에서 브라우저가 열리고 사용자가 승인해야 합니다.
        genai_client = configure_genai()
        print("인증 성공! 'token.json'이 생성되었습니다.")

        print("\n--- 모델 목록 및 정보 확인 ---")
        # 사용 가능한 모델 목록 출력
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"Model: {m.name}, Display Name: {m.display_name}")

        print("\n--- 구독자 한도(Quota) 테스트 ---")
        # 간단한 테스트 요청
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content("Hello, can you confirm if my subscriber benefits are active?")
        print(f"Response: {response.text[:200]}...")
        
        # Quota 정보는 현재 직접적으로 API에서 조회하기 어려우나, 
        # 특정 모델(예: Pro 1.5)에 대한 접근 가능 여부로 간접 확인 가능.
        print("\nGemini 1.5 Pro 모델 접근 테스트...")
        try:
            pro_model = genai.GenerativeModel("gemini-1.5-pro")
            pro_response = pro_model.generate_content("Test message")
            print("Gemini 1.5 Pro 접근 성공.")
        except Exception as e:
            print(f"Gemini 1.5 Pro 접근 실패 (한도 혹은 접근 권한 문제): {e}")

    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    test_auth()
