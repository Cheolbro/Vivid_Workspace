"""
YouTube 채널 양산형 콘텐츠 정책 위반 가능성 분석 스크립트.

수집:
  - channels.list            : 채널 메타(제목, 설명, 통계, uploads 플레이리스트 ID)
  - playlistItems.list       : uploads 플레이리스트 -> 모든 videoId
  - videos.list              : 영상별 snippet / statistics / contentDetails

분석:
  - 제목 템플릿 유사도(포맷 패턴 / 접두·접미사 중복)
  - 설명란 중복률(shingling 기반 Jaccard)
  - 태그 중복률
  - 영상 길이(duration) 분포 균일성
  - 업로드 간격 분포 (대량 생산 시그널)
  - 썸네일은 URL 기반이라 외형 비교 불가 -> URL 해시 중복만 점검

결과:
  - audit_raw.json     : API 응답 원본(영상 리스트)
  - audit_report.md    : 사람이 읽는 최종 리포트
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API_KEY = "AIzaSyAdf38NPvEnkOFrS8CDt1ZKN6nJZZLT_bQ"
CHANNEL_ID = "UClnNxyKqrrdyxzHO5vbJMxA"
BASE = "https://www.googleapis.com/youtube/v3"
OUT_DIR = Path(__file__).resolve().parent
RAW_PATH = OUT_DIR / "audit_raw.json"
REPORT_PATH = OUT_DIR / "audit_report.md"


def _get(endpoint: str, **params: Any) -> dict:
    params["key"] = API_KEY
    resp = requests.get(f"{BASE}/{endpoint}", params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"{endpoint} {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def fetch_channel() -> dict:
    data = _get(
        "channels",
        part="snippet,statistics,contentDetails,brandingSettings,topicDetails",
        id=CHANNEL_ID,
    )
    if not data.get("items"):
        raise RuntimeError("채널 정보를 찾을 수 없습니다.")
    return data["items"][0]


def fetch_all_video_ids(uploads_playlist_id: str) -> list[str]:
    ids: list[str] = []
    page = None
    while True:
        params = dict(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
        )
        if page:
            params["pageToken"] = page
        data = _get("playlistItems", **params)
        for it in data.get("items", []):
            vid = it["contentDetails"].get("videoId")
            if vid:
                ids.append(vid)
        page = data.get("nextPageToken")
        if not page:
            break
    return ids


def fetch_videos(video_ids: list[str]) -> list[dict]:
    all_items: list[dict] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        data = _get(
            "videos",
            part="snippet,statistics,contentDetails,status,topicDetails",
            id=",".join(chunk),
        )
        all_items.extend(data.get("items", []))
    return all_items


# -------------------- 분석 헬퍼 --------------------

ISO_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_duration(iso: str) -> int:
    """ISO8601 -> 초."""
    m = ISO_DUR.match(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def shingles(text: str, k: int = 4) -> set[str]:
    t = re.sub(r"\s+", " ", (text or "").lower()).strip()
    toks = t.split(" ")
    if len(toks) < k:
        return {t} if t else set()
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    u = a | b
    if not u:
        return 0.0
    return len(a & b) / len(u)


def title_skeleton(title: str) -> str:
    """숫자/영문 토큰을 자리표시자로 치환해 '템플릿 골격'을 추출."""
    t = re.sub(r"\d+", "#", title or "")
    t = re.sub(r"[A-Za-z]{2,}", "W", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def common_affix(titles: list[str], prefix: bool) -> tuple[str, int]:
    """가장 흔한 접두(또는 접미) N글자(최대 12) 반환."""
    if not titles:
        return "", 0
    best = ("", 0)
    for n in range(12, 1, -1):
        counts = Counter()
        for t in titles:
            if len(t) < n:
                continue
            seg = t[:n] if prefix else t[-n:]
            counts[seg] += 1
        if not counts:
            continue
        seg, cnt = counts.most_common(1)[0]
        if cnt >= max(3, len(titles) // 10) and cnt > best[1]:
            best = (seg, cnt)
        if best[1] >= len(titles) // 3:
            break
    return best


# -------------------- 분석 본체 --------------------


def analyze(channel: dict, videos: list[dict]) -> str:
    snip = channel["snippet"]
    stats = channel["statistics"]
    channel_title = snip.get("title", "")
    channel_desc = snip.get("description", "") or ""
    published = snip.get("publishedAt", "")
    sub_count = stats.get("subscriberCount", "?")
    view_total = stats.get("viewCount", "?")
    video_count_api = stats.get("videoCount", "?")

    n = len(videos)

    # 영상별 파생 필드
    rows = []
    for v in videos:
        sn = v.get("snippet", {})
        cd = v.get("contentDetails", {})
        st = v.get("statistics", {})
        dur = parse_duration(cd.get("duration", "PT0S"))
        rows.append(
            {
                "id": v.get("id"),
                "title": sn.get("title", ""),
                "description": sn.get("description", "") or "",
                "tags": sn.get("tags", []) or [],
                "publishedAt": sn.get("publishedAt", ""),
                "duration": dur,
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "comments": int(st.get("commentCount", 0) or 0),
                "thumb": (sn.get("thumbnails", {}).get("high", {}) or {}).get("url", ""),
                "category": sn.get("categoryId", ""),
                "live": sn.get("liveBroadcastContent", "none"),
            }
        )
    rows.sort(key=lambda r: r["publishedAt"])

    # ---- 1) 제목 템플릿 ----
    skeletons = Counter(title_skeleton(r["title"]) for r in rows)
    top_skeletons = skeletons.most_common(10)
    repeat_skel_share = (
        sum(c for _, c in top_skeletons if c >= 2) / n if n else 0
    )
    prefix_hit = common_affix([r["title"] for r in rows], prefix=True)
    suffix_hit = common_affix([r["title"] for r in rows], prefix=False)

    # ---- 2) 설명 중복 (설명이 매우 짧은 채널 포함 대응) ----
    desc_len = [len(r["description"]) for r in rows]
    empty_desc = sum(1 for r in rows if len(r["description"].strip()) < 20)
    desc_shingles = [shingles(r["description"], k=4) for r in rows]
    # 전수 비교는 O(n^2). n이 과대할 경우 샘플링(최근 200).
    sample_idx = list(range(len(rows)))
    if len(sample_idx) > 200:
        sample_idx = sample_idx[-200:]
    pair_sims: list[float] = []
    high_sim_pairs = 0
    for i_pos, i in enumerate(sample_idx):
        for j in sample_idx[i_pos + 1 :]:
            s = jaccard(desc_shingles[i], desc_shingles[j])
            pair_sims.append(s)
            if s >= 0.8:
                high_sim_pairs += 1
    desc_avg_sim = statistics.mean(pair_sims) if pair_sims else 0.0
    desc_median_sim = statistics.median(pair_sims) if pair_sims else 0.0

    # ---- 3) 태그 중복률 ----
    all_tag_sets = [set(t.lower() for t in r["tags"]) for r in rows]
    pair_tag_sims: list[float] = []
    for i_pos, i in enumerate(sample_idx):
        for j in sample_idx[i_pos + 1 :]:
            pair_tag_sims.append(jaccard(all_tag_sets[i], all_tag_sets[j]))
    tag_avg_sim = statistics.mean(pair_tag_sims) if pair_tag_sims else 0.0

    # ---- 4) 영상 길이 분포 ----
    durs = [r["duration"] for r in rows if r["duration"] > 0]
    if durs:
        dur_mean = statistics.mean(durs)
        dur_stdev = statistics.stdev(durs) if len(durs) > 1 else 0.0
        dur_cv = (dur_stdev / dur_mean) if dur_mean else 0.0  # 변동계수
    else:
        dur_mean = dur_stdev = dur_cv = 0.0

    # ---- 5) 업로드 간격 ----
    times = []
    for r in rows:
        try:
            times.append(datetime.fromisoformat(r["publishedAt"].replace("Z", "+00:00")))
        except Exception:
            pass
    gaps_hours = []
    for a, b in zip(times, times[1:]):
        gaps_hours.append((b - a).total_seconds() / 3600.0)
    gap_med = statistics.median(gaps_hours) if gaps_hours else 0.0
    bursts_1h = sum(1 for g in gaps_hours if g < 1)
    bursts_6h = sum(1 for g in gaps_hours if g < 6)

    # ---- 6) 썸네일 URL 중복 ----
    thumb_counter = Counter(r["thumb"] for r in rows if r["thumb"])
    dup_thumbs = [(u, c) for u, c in thumb_counter.items() if c > 1]

    # ---- 7) 조회/반응 대비 ----
    views = [r["views"] for r in rows]
    zero_engage = sum(1 for r in rows if (r["likes"] + r["comments"]) == 0)

    # ---- 종합 점수 ----
    # 높을수록 위험. 근거 있는 heuristic 합산(각 항목 0~1 스케일).
    score_parts = {
        "제목 템플릿 반복률": min(repeat_skel_share * 2.0, 1.0),
        "설명 평균 유사도": min(desc_avg_sim * 1.25, 1.0),
        "태그 평균 유사도": min(tag_avg_sim * 1.25, 1.0),
        "영상길이 균일성(1-변동계수)": max(0.0, 1.0 - dur_cv) if durs else 0.0,
        "업로드 버스트 비율": min((bursts_6h / max(1, len(gaps_hours))) * 2.0, 1.0),
        "빈약한 설명 비율": (empty_desc / n) if n else 0.0,
    }
    risk_score = sum(score_parts.values()) / len(score_parts)

    def level(x: float) -> str:
        if x >= 0.6:
            return "HIGH (높음)"
        if x >= 0.35:
            return "MEDIUM (중간)"
        return "LOW (낮음)"

    # ---- 리포트 ----
    lines: list[str] = []
    w = lines.append
    w(f"# YouTube 채널 양산형 콘텐츠 정책 위반 가능성 감사\n")
    w(f"- 생성: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    w(f"- 채널: **{channel_title}** (`{CHANNEL_ID}`)")
    w(f"- 개설일: {published}")
    w(
        f"- 구독자: {sub_count} / 누적 조회: {view_total} / 영상(공개+비공개 포함 API 카운트): {video_count_api}"
    )
    w(f"- 수집된 영상 수: **{n}**\n")

    w("## 1. 종합 평가")
    w(f"- 종합 리스크 점수: **{risk_score:.2f} / 1.00 → {level(risk_score)}**")
    w("")
    w("| 지표 | 값 | 해석 |")
    w("|---|---|---|")
    for k, v in score_parts.items():
        w(f"| {k} | {v:.2f} | {level(v)} |")
    w("")

    w("## 2. 채널 메타")
    w(f"- 채널 설명 길이: {len(channel_desc)}자 (비어있거나 너무 짧으면 '정보' 섹션 감점 요인)")
    if channel_desc:
        preview = channel_desc.strip().splitlines()[0][:160]
        w(f"- 채널 설명 첫 줄: `{preview}`")
    w("")

    w("## 3. 제목 패턴 (양산형 핵심 시그널)")
    w(f"- 전체 영상 중 동일 '골격'을 공유하는 영상 비율: **{repeat_skel_share:.1%}**")
    w(f"- 가장 흔한 제목 골격 Top 10 (숫자는 `#`, 영단어는 `W`로 치환):")
    for skel, cnt in top_skeletons:
        w(f"  - `{skel}` × {cnt}")
    if prefix_hit[1]:
        w(f"- 반복 접두사: `{prefix_hit[0]}` × {prefix_hit[1]}회")
    if suffix_hit[1]:
        w(f"- 반복 접미사: `{suffix_hit[0]}` × {suffix_hit[1]}회")
    w("")

    w("## 4. 설명란(Description)")
    w(f"- 평균 길이: {statistics.mean(desc_len):.0f}자 / 중앙값: {statistics.median(desc_len):.0f}자")
    w(f"- 설명이 20자 미만인 영상: {empty_desc}개 ({empty_desc / n:.1%})" if n else "- N/A")
    w(f"- 설명 pair 유사도 평균: {desc_avg_sim:.2f} / 중앙값: {desc_median_sim:.2f}")
    w(f"- Jaccard ≥ 0.80 고유사 pair 수: {high_sim_pairs}")
    w("")

    w("## 5. 태그 중복")
    w(f"- pair 평균 Jaccard: {tag_avg_sim:.2f}")
    tag_counter: Counter = Counter()
    for ts in all_tag_sets:
        tag_counter.update(ts)
    if tag_counter:
        w("- 전 채널 최다 사용 태그 Top 10:")
        for t, c in tag_counter.most_common(10):
            w(f"  - `{t}` × {c}")
    else:
        w("- 태그 미사용")
    w("")

    w("## 6. 영상 길이 분포")
    if durs:
        w(f"- 평균: {dur_mean:.0f}초 ({dur_mean / 60:.1f}분) / 표준편차: {dur_stdev:.0f}초")
        w(f"- 변동계수(낮을수록 균일): {dur_cv:.2f}")
        buckets = {
            "Shorts(<=60s)": sum(1 for d in durs if d <= 60),
            "1~3분": sum(1 for d in durs if 60 < d <= 180),
            "3~10분": sum(1 for d in durs if 180 < d <= 600),
            "10~30분": sum(1 for d in durs if 600 < d <= 1800),
            "30분+": sum(1 for d in durs if d > 1800),
        }
        for k, c in buckets.items():
            w(f"  - {k}: {c}개 ({c / len(durs):.1%})")
    w("")

    w("## 7. 업로드 리듬")
    if gaps_hours:
        w(f"- 업로드 간격 중앙값: {gap_med:.1f}시간")
        w(f"- 1시간 이내 연속 업로드: {bursts_1h}회")
        w(f"- 6시간 이내 연속 업로드: {bursts_6h}회 (버스트 업로드 시그널)")
    w("")

    w("## 8. 썸네일 중복")
    if dup_thumbs:
        w(f"- URL이 동일한 썸네일: {len(dup_thumbs)}건")
        for u, c in dup_thumbs[:5]:
            w(f"  - `{u}` × {c}")
    else:
        w("- 동일 URL 썸네일 없음 (단, 외형 유사도는 본 스크립트로 판정 불가)")
    w("")

    w("## 9. 참여도(보조 지표)")
    if views:
        w(f"- 조회수 중앙값: {int(statistics.median(views))}")
        w(f"- 좋아요/댓글 모두 0인 영상: {zero_engage}개 ({zero_engage / n:.1%})")
    w("")

    w("## 10. 정책 항목별 매핑")
    w(
        "- **양산형(=중복/템플릿):** 제목 골격 반복률·설명 유사도·태그 유사도·길이 변동계수 → 1·3·4·5·6 섹션."
    )
    w(
        "- **재사용된 콘텐츠:** 본 스크립트는 원본 판별 불가. 썸네일 URL 중복(§8), 참여도가 기형적으로 낮은 영상 다수(§9)일 때 수작업 샘플링 권장."
    )
    w(
        "- **교육/해설 가치 부재:** 평균 설명 길이·빈약 설명 비율이 높고, 영상 길이가 매우 짧고 균일하면 슬라이드쇼/스크롤텍스트형 의심. §4, §6 교차 확인."
    )
    w("")

    w("## 11. 조치 권고")
    rec = []
    if score_parts["제목 템플릿 반복률"] >= 0.35:
        rec.append(
            "제목 템플릿을 3종 이상으로 다양화하고, 영상별로 고유 포인트(숫자/고유명사/주장)를 반영."
        )
    if score_parts["설명 평균 유사도"] >= 0.35:
        rec.append(
            "설명란의 채널 공통 문구를 하단으로 분리하고, 상단 2~3문장은 영상마다 고유한 요약으로 교체."
        )
    if score_parts["태그 평균 유사도"] >= 0.5:
        rec.append("공통 태그 5개 + 영상별 고유 태그 5개 이상으로 구성.")
    if score_parts["영상길이 균일성(1-변동계수)"] >= 0.7:
        rec.append(
            "영상 길이를 의도적으로 다양화(길이가 거의 동일하면 템플릿 생산으로 읽힐 수 있음)."
        )
    if score_parts["업로드 버스트 비율"] >= 0.35:
        rec.append(
            "단시간 대량 업로드(6시간 내 연속 다수) 패턴을 줄이고, 하루 1~2개 이하로 스케줄 조정."
        )
    if score_parts["빈약한 설명 비율"] >= 0.35:
        rec.append(
            "모든 영상에 고유 해설/컨텍스트(최소 3~4문장)를 추가 — '슬라이드쇼/스크롤 텍스트' 판정을 방어."
        )
    if not rec:
        rec.append("정량 지표상 뚜렷한 양산형 신호 없음. 정성 검수(상위 10개·최신 10개)만 병행.")
    for r in rec:
        w(f"- {r}")
    w("")

    w("## 12. 가장 의심되는 영상 샘플 (수작업 검수용)")
    # (a) 제목 골격이 Top1과 동일하면서 조회수가 낮은 영상
    top_skel = top_skeletons[0][0] if top_skeletons else ""
    suspects = [
        r for r in rows if title_skeleton(r["title"]) == top_skel
    ]
    suspects.sort(key=lambda r: r["views"])
    for r in suspects[:10]:
        w(
            f"- [{r['title']}](https://youtu.be/{r['id']}) — 조회 {r['views']}, 길이 {r['duration']}s, 업로드 {r['publishedAt'][:10]}"
        )

    return "\n".join(lines)


def main() -> int:
    print("[1/3] 채널 메타 수집...", flush=True)
    channel = fetch_channel()
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"      uploads 플레이리스트: {uploads}", flush=True)

    print("[2/3] 영상 ID 전체 수집...", flush=True)
    ids = fetch_all_video_ids(uploads)
    print(f"      영상 {len(ids)}개", flush=True)

    print("[3/3] videos.list 상세 조회...", flush=True)
    videos = fetch_videos(ids)
    print(f"      상세 {len(videos)}개 확보", flush=True)

    RAW_PATH.write_text(
        json.dumps(
            {"channel": channel, "videos": videos},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = analyze(channel, videos)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n완료: {REPORT_PATH}", flush=True)
    print(f"원본: {RAW_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
