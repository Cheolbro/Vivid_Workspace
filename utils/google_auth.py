"""
utils/google_auth.py
Google OAuth2 흐름으로 인증하고, google.genai Client를 반환한다.

함수:
    get_credentials(...)   -> google.oauth2.credentials.Credentials
    get_genai_client(...)  -> google.genai.Client  (신규 SDK)

의존 패키지:
    pip install google-auth google-auth-oauthlib google-genai
"""

from pathlib import Path

# 워크스페이스 루트 (utils/ 의 부모)
_ROOT_DIR = Path(__file__).parent.parent

# 기본 파일 경로 (절대 경로)
_DEFAULT_CLIENT_SECRET = _ROOT_DIR / "client_secret.json"
_DEFAULT_TOKEN          = _ROOT_DIR / "token.json"

# Gemini API OAuth 스코프
# https://ai.google.dev/gemini-api/docs/oauth
SCOPES = ["https://www.googleapis.com/auth/generative-language.peruserquota"]


def get_credentials(
    client_secret_path=None,
    token_path=None,
):
    """
    OAuth2 인증을 수행하고 Credentials 객체를 반환한다.
    인증 정보는 token_path에 캐시하여 재사용한다.

    Args:
        client_secret_path: client_secret.json 경로. 미지정 시 ROOT_DIR 사용.
        token_path:         토큰 캐시 경로. 미지정 시 ROOT_DIR/token.json 사용.

    Raises:
        ImportError:       google-auth 또는 google-auth-oauthlib 미설치 시.
        FileNotFoundError: client_secret.json 이 없을 때.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ImportError(
            "Google OAuth 라이브러리가 설치되어 있지 않습니다.\n"
            "터미널에서 아래 명령어를 실행해 설치하세요:\n"
            "  pip install google-auth google-auth-oauthlib"
        ) from exc

    client_secret_path = Path(client_secret_path) if client_secret_path else _DEFAULT_CLIENT_SECRET
    token_path         = Path(token_path)          if token_path          else _DEFAULT_TOKEN

    creds = None

    # 캐시된 토큰 로드
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # 토큰이 없거나 만료된 경우
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    f"'{client_secret_path}' 파일이 없습니다.\n"
                    "Google Cloud Console에서 OAuth 클라이언트 ID를 발급받아\n"
                    "프로젝트 루트(Vivid_Workspace/)에 저장해주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), SCOPES
            )
            # 브라우저가 자동으로 열려 로그인 후 토큰 발급
            creds = flow.run_local_server(port=0, open_browser=True)

        # 갱신된 토큰 저장 (다음 실행 시 재사용)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_genai_client(
    client_secret_path=None,
    token_path=None,
):
    """
    OAuth2 credentials를 사용하여 google.genai Client를 반환한다.
    (신규 google-genai SDK 전용)

    Args:
        client_secret_path: client_secret.json 경로. 미지정 시 ROOT_DIR 사용.
        token_path:         토큰 캐시 경로. 미지정 시 ROOT_DIR/token.json 사용.

    Returns:
        google.genai.Client (인증 완료 상태)

    Raises:
        ImportError:       google-genai 미설치 시.
        FileNotFoundError: client_secret.json 이 없을 때.
    """
    try:
        from google import genai  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "google-genai 라이브러리가 설치되어 있지 않습니다.\n"
            "터미널에서 아래 명령어를 실행해 설치하세요:\n"
            "  pip install google-genai"
        ) from exc

    creds = get_credentials(client_secret_path, token_path)
    return genai.Client(credentials=creds)
