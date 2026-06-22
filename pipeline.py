#!/usr/bin/env python3
"""
슬랙 KOL 브리핑 → 로컬 저장 (티스토리 수동 등록용)
======================================================

티스토리 자동 발행 대신 수동 등록에 필요한 파일들을 로컬에 저장합니다.

저장 위치: output/YYYY-MM-DD/
  tistory_body.html   – 티스토리 HTML 에디터에 붙여넣을 본문
  preview.html        – 브라우저 미리보기용 전체 페이지
  meta.json           – 제목·태그·요약
  header_image.jpg    – 대표 이미지 (있을 경우)
  posting_guide.txt   – 수동 등록 순서 안내

티스토리 등록 방법 (HTML 모드):
  글쓰기 → 에디터 'HTML' 버튼 클릭 → tistory_body.html 내용 붙여넣기 → 일반 모드 복귀

필요 패키지: pip install requests python-dotenv
환경변수(.env): SLACK_BOT_TOKEN, SLACK_CHANNEL_ID
               (선택) MEDIA_DIR, HEADER_IMAGE_PATH, TISTORY_BLOG_NAME
"""

import io
import os
import sys
import re
import html
import json
import argparse
import datetime
from pathlib import Path

import requests

try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("./output")
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "./media"))
TISTORY_CATEGORY = os.environ.get("TISTORY_CATEGORY", "KOL리포트")

INTRO = "이 게시물은 최근 24시간 동안 텔레그램 국내 탑 200여 개 KOL들의 포스팅을 분석·요약한 보고서입니다."

SLACK_EMOJI = {
    ":satellite_antenna:": "📡", ":fire:": "🔥", ":repeat:": "🔁", ":mega:": "📢",
    ":eyes:": "👀", ":bar_chart:": "📊", ":white_check_mark:": "✅",
    ":rotating_light:": "🚨", ":pushpin:": "📌", ":bulb:": "💡", ":bell:": "🔔",
    ":rocket:": "🚀", ":chart_with_upwards_trend:": "📈",
    ":chart_with_downwards_trend:": "📉",
    ":handshake:": "🤝", ":robot_face:": "🤖", ":warning:": "⚠️",
    ":clipboard:": "📋", ":moneybag:": "💰", ":dart:": "🎯", ":memo:": "📝",
    ":calendar:": "📅", ":zap:": "⚡", ":star:": "⭐", ":speech_balloon:": "💬",
    ":loudspeaker:": "📢", ":link:": "🔗", ":mag:": "🔍",
    ":arrow_up:": "⬆️", ":arrow_down:": "⬇️", ":red_circle:": "🔴",
    ":large_green_circle:": "🟢", ":large_yellow_circle:": "🟡",
    ":trophy:": "🏆", ":gem:": "💎", ":bank:": "🏦", ":chart:": "📊",
    ":newspaper:": "📰", ":electric_plug:": "🔌", ":hammer:": "🔨",
}
HEADER_EMOJIS = ("🔥", "🔁", "📢", "👀", "📊", "🚀", "🚨",
                 "📈", "📉", "🔔", "💡", "📌", "🆕")
WEAK_TAGS = {"급등", "유동성", "선물", "공격", "볼트", "8000선", "숨고르기", "동반"}
FOOTER_MARKERS = ("다음을 사용하여 보냄",)

ST_H2 = "font-size:20px;font-weight:700;margin:30px 0 12px;line-height:1.4;"
ST_TITLE = "font-size:16px;font-weight:700;margin:18px 0 4px;line-height:1.5;"
ST_P = "font-size:15px;line-height:1.75;margin:8px 0;"
ST_SRC = "font-size:13px;color:#888888;margin:2px 0 12px;"
ST_LI = "font-size:15px;line-height:1.75;margin:6px 0;"
ST_LEAD = ("font-size:15px;line-height:1.75;margin:0 0 18px;padding:10px 14px;"
           "background:#f6f8fa;border-left:3px solid #2d6cdf;color:#333333;")


# ---------------------------------------------------------------------------
# 슬랙 읽기
# ---------------------------------------------------------------------------
def fetch_briefing_from_slack() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        sys.exit("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID 환경변수를 설정하세요.")
    resp = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {token}"},
        params={"channel": channel, "limit": 15},
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok"):
        sys.exit(f"슬랙 읽기 실패: {data.get('error')} (봇 채널 초대/history 권한 확인)")
    for msg in data.get("messages", []):
        t = msg.get("text", "")
        if "핵심 이슈" in t or "데일리 브리핑" in t or "모니터링" in t:
            return t
    msgs = data.get("messages", [])
    if msgs:
        return msgs[0].get("text", "")
    sys.exit("슬랙 채널에서 메시지를 찾지 못했습니다.")


# ---------------------------------------------------------------------------
# 원문 → HTML
# ---------------------------------------------------------------------------
def _normalize_slack(text: str) -> str:
    text = re.sub(r"<([^|>]+)\|([^>]+)>", r"\2 (\1)", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def _emojify(text: str) -> str:
    for code, emo in SLACK_EMOJI.items():
        text = text.replace(code, emo)
    return text


def _strip_emphasis(s: str) -> str:
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"_(.+?)_", r"\1", s)
    return s


def _is_header(s: str) -> bool:
    return s.startswith(HEADER_EMOJIS) or s.startswith("■")


def _linkify(text: str) -> str:
    def repl(m):
        url = m.group(0).rstrip(").,")
        tm = re.search(r"t\.me/([^/\s)]+)", url)
        return f"<a href='{url}'>{('@' + tm.group(1)) if tm else url}</a>"
    return re.sub(r"https?://[^\s)]+", repl, text)


def _fmt(s: str) -> str:
    return _linkify(html.escape(s, quote=False))


def _is_divider(s: str) -> bool:
    return bool(re.fullmatch(r"[━─\-—=•·\s]{6,}", s))


def _slack_to_html(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*([^*\n]+)\*", r"<strong>\1</strong>", s)
    s = re.sub(r"_([^_\n]+)_", r"<em>\1</em>", s)
    return _linkify(s)


def _render_source_line(src: str) -> str:
    prefix, rest = ("출처: ", src[src.index(":")+1:].strip()) if ":" in src else ("", src)
    parts = []
    for p in re.split(r"\s*\|\s*|\s*,\s*", rest):
        p = p.strip()
        if not p:
            continue
        m = re.match(r"^(.+?)\s*\((https?://\S+?)\)$", p)
        if m:
            parts.append(f"<a href='{m.group(2)}'>{html.escape(m.group(1))}</a>")
        elif re.match(r"^https?://", p):
            tm = re.search(r"t\.me/([^/\s)]+)", p)
            label = ("@" + tm.group(1)) if tm else p
            parts.append(f"<a href='{p}'>{html.escape(label)}</a>")
        elif re.fullmatch(r"[A-Za-z0-9_]{3,}", p):
            parts.append(f"<a href='https://t.me/{p}'>@{p}</a>")
        else:
            parts.append(html.escape(p))
    return prefix + " | ".join(parts)


def report_to_html(text: str):
    INTERNAL = (
        "고객 후보군", "제안영업", "기초자료로 사용하기", "협업 제안의 기초자료",
        "이 게시물은 최근 24시간",
    )

    lines = _emojify(text).splitlines()
    out, first_title, ul_open = [], [None], [False]

    def close_ul():
        if ul_open[0]:
            out.append("</ul>")
            ul_open[0] = False

    for raw in lines:
        raw_s = raw.strip()
        if not raw_s or _is_divider(raw_s):
            close_ul()
            continue
        if any(mk in raw_s for mk in FOOTER_MARKERS):
            continue
        if any(p in raw_s for p in INTERNAL):
            continue
        if re.search(r"<@U[A-Z0-9]+>", raw_s):
            continue

        s_plain = _strip_emphasis(raw_s)
        s_clean = re.sub(r":[a-z0-9_+\-]+:", "", s_plain).strip()
        if re.search(r"(데일리 브리핑|KOL 브리핑|모니터링 브리핑)", s_clean) and re.search(r"\d{4}", s_clean):
            if first_title[0] is None:
                first_title[0] = re.sub(r"\s*[|—]\s*\d.*$", "", s_clean).strip()
            continue

        if _is_header(s_plain):
            close_ul()
            clean = re.sub(r"^[■▶▷◆◇\s]+", "", s_plain).strip()
            if first_title[0] is None:
                first_title[0] = clean
            out.append(f"<h2 style='{ST_H2}'>{html.escape(clean)}</h2>")
            continue

        if re.match(r"^[•‣▪]\s*", raw_s):
            inner_raw = re.sub(r"^[•‣▪]\s*", "", raw_s)
            inner_plain = _strip_emphasis(inner_raw)
            if re.match(r"^출처\s*:", inner_plain):
                close_ul()
                out.append(f"<p style='{ST_SRC}'>{_render_source_line(inner_plain)}</p>")
            else:
                if not ul_open[0]:
                    out.append("<ul>")
                    ul_open[0] = True
                out.append(f"<li style='{ST_LI}'>{_slack_to_html(inner_raw)}</li>")
            continue

        close_ul()

        if re.match(r"^\*?\d+\.\*?\s+", raw_s):
            out.append(f"<p style='{ST_TITLE}'>{_slack_to_html(raw_s)}</p>")
            continue

        if re.match(r"^출처\s*:", s_plain):
            out.append(f"<p style='{ST_SRC}'>{_render_source_line(s_plain)}</p>")
            continue

        out.append(f"<p style='{ST_P}'>{_slack_to_html(raw_s)}</p>")

    close_ul()
    return "\n".join(out), first_title[0]


def extract_hashtags(text: str, minimum: int = 5, cap: int = 8):
    found = []
    for line in text.splitlines():
        s = _strip_emphasis(line.strip())
        if s.startswith(("키워드:", "키워드 :")):
            for kw in re.split(r"[,/·]", s.split(":", 1)[1]):
                t = kw.strip().lstrip("$").replace(" ", "").replace("#", "")
                if len(t) >= 2 and t not in found and t not in WEAK_TAGS:
                    found.append(t)
    for fb in ("비트코인", "크립토", "블록체인", "시장분석", "KOL"):
        if len(found) >= minimum:
            break
        if fb not in found:
            found.append(fb)
    return found[:cap]


def format_briefing(briefing_text: str, post_date: str) -> dict:
    text = _normalize_slack(briefing_text)
    body_html, first_title = report_to_html(text)
    hashtags = extract_hashtags(text)

    lead = f"<p style='{ST_LEAD}'><em>{html.escape(INTRO)}</em></p>"
    tag_line = "<p style='font-size:14px;color:#666;margin:16px 0;'>" + " ".join(f"#{h}" for h in hashtags) + "</p>"
    html_body = f"{lead}\n{body_html}\n<hr>\n{tag_line}"

    clean_title = re.sub(r"[^\w\s가-힣a-zA-Z0-9\-\—·]", "", first_title).strip() if first_title else None
    clean_title = re.sub(r"\s+", " ", clean_title).strip() if clean_title else None
    title = (f"{clean_title} | 텔레그램 KOL 브리핑 {post_date}"
             if clean_title else f"텔레그램 KOL 브리핑 {post_date}")
    m = re.search(r"https?://t\.me/\S+", text)
    lead_url = m.group(0).rstrip(").,") if m else None

    return {
        "title": title,
        "tags": hashtags,
        "summary": INTRO[:300],
        "lead_source_url": lead_url,
        "html_body": html_body,
    }


# ---------------------------------------------------------------------------
# 헤더 이미지 다운로드
# ---------------------------------------------------------------------------
_IMG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_IMG_MAX_WIDTH = 1200


def _ext_from_bytes(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _resize_if_needed(data: bytes) -> bytes:
    if not _PIL_AVAILABLE:
        return data
    try:
        img = PILImage.open(io.BytesIO(data)).convert("RGB")
        if img.width > _IMG_MAX_WIDTH:
            h = int(img.height * _IMG_MAX_WIDTH / img.width)
            img = img.resize((_IMG_MAX_WIDTH, h), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue()
    except Exception as e:
        print(f"  (이미지 리사이즈 실패, 원본 사용: {e})", file=sys.stderr)
        return data


def _fetch_telegram_embed_image(channel: str, post_id: str):
    embed_url = f"https://t.me/{channel}/{post_id}?embed=1&single=1"
    try:
        resp = requests.get(embed_url, headers=_IMG_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        html_text = resp.text
        m = re.search(
            r'tgme_widget_message_photo_wrap[^>]*style="[^"]*'
            r"background-image:url\('([^']+)'\)",
            html_text,
        )
        if not m:
            m = re.search(r'<video[^>]+poster="(https://[^"]+)"', html_text)
        if not m:
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html_text)
        if not m:
            return None
        img_url = html.unescape(m.group(1))
        img_resp = requests.get(img_url, headers=_IMG_HEADERS, timeout=20)
        if img_resp.status_code == 200 and len(img_resp.content) > 1024:
            return img_resp.content
    except Exception as e:
        print(f"  (임베드 파싱 오류 {channel}/{post_id}: {e})", file=sys.stderr)
    return None


def _fetch_via_bot_api(channel: str, post_id: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return None
    try:
        chat = f"@{channel}" if not channel.startswith("@") else channel
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMessages",
            params={"chat_id": chat, "message_ids": post_id},
            timeout=15,
        )
        data = r.json()
        if not data.get("ok"):
            return None
        msg = (data.get("result") or [{}])[0]
        photo = msg.get("photo") or []
        if not photo:
            doc = msg.get("document", {})
            if (doc.get("mime_type", "")).startswith("image/"):
                photo = [doc]
        if not photo:
            return None
        best = max(photo, key=lambda p: p.get("file_size", 0))
        file_id = best.get("file_id", "")
        if not file_id:
            return None
        r2 = requests.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        fpath = r2.json().get("result", {}).get("file_path", "")
        if not fpath:
            return None
        r3 = requests.get(
            f"https://api.telegram.org/file/bot{token}/{fpath}",
            headers=_IMG_HEADERS,
            timeout=30,
        )
        if r3.status_code == 200:
            return r3.content
    except Exception as e:
        print(f"  (Bot API 다운로드 실패: {e})", file=sys.stderr)
    return None


def download_header_image(text: str, post_date: str):
    """브리핑 첫 번째 t.me 포스트에서 이미지를 다운로드해 MEDIA_DIR 에 캐시."""
    existing = list(MEDIA_DIR.glob(f"{post_date}_header.*"))
    if existing:
        print(f"  · 헤더 이미지 캐시 있음: {existing[0]}", file=sys.stderr)
        return existing[0]

    urls = re.findall(r"https?://t\.me/[^/\s)>\"']+/\d+", text)
    if not urls:
        return None

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    for url in urls[:8]:
        url = url.rstrip(").,")
        mm = re.search(r"t\.me/([^/?#]+)/(\d+)", url)
        if not mm:
            continue
        channel, post_id = mm.group(1), mm.group(2)
        print(f"  · 이미지 시도: @{channel}/{post_id}", file=sys.stderr)

        data = _fetch_via_bot_api(channel, post_id) or _fetch_telegram_embed_image(channel, post_id)
        if not data:
            continue

        data = _resize_if_needed(data)
        ext = "jpg" if _PIL_AVAILABLE else _ext_from_bytes(data)
        out_path = MEDIA_DIR / f"{post_date}_header.{ext}"
        out_path.write_bytes(data)
        print(f"  · 헤더 이미지 저장: {out_path} ({len(data) // 1024}KB)", file=sys.stderr)
        return out_path

    print("  (텔레그램 이미지 없음 — 이미지 없이 진행)", file=sys.stderr)
    return None


def load_header_image(post_date: str, lead_url: str):
    candidates = []
    env = os.environ.get("HEADER_IMAGE_PATH")
    if env:
        candidates.append(Path(env))
    candidates += sorted(MEDIA_DIR.glob(f"{post_date}_header.*"))
    candidates += sorted(MEDIA_DIR.glob("header.*"))
    if lead_url:
        mm = re.search(r"t\.me/([^/?#]+)/(\d+)", lead_url)
        if mm:
            candidates += sorted(MEDIA_DIR.glob(f"{mm.group(1)}_{mm.group(2)}.*"))
    for p in candidates:
        try:
            if p and p.exists():
                return p.read_bytes()
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
# 로컬 파일 저장
# ---------------------------------------------------------------------------
def save_output(post: dict, post_date: str, image_bytes=None) -> Path:
    """결과 파일을 output/YYYY-MM-DD/ 폴더에 저장."""
    day_dir = OUTPUT_DIR / post_date
    day_dir.mkdir(parents=True, exist_ok=True)

    # 1. 티스토리 HTML 본문 (에디터 HTML 모드에 붙여넣을 내용)
    (day_dir / "tistory_body.html").write_text(post["html_body"], encoding="utf-8")

    # 2. 브라우저 미리보기용 전체 페이지
    (day_dir / "preview.html").write_text(
        _build_preview_html(post, post_date), encoding="utf-8"
    )

    # 3. 제목·태그·요약 메타데이터
    (day_dir / "meta.json").write_text(
        json.dumps(
            {k: post.get(k) for k in ("title", "tags", "summary")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 4. 대표 이미지
    if image_bytes:
        (day_dir / "header_image.jpg").write_bytes(image_bytes)

    # 5. 수동 등록 안내
    (day_dir / "posting_guide.txt").write_text(
        _build_posting_guide(post, post_date, bool(image_bytes)),
        encoding="utf-8",
    )

    return day_dir


def _build_preview_html(post: dict, post_date: str) -> str:
    tags_str = " ".join(f"#{t}" for t in post.get("tags", []))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(post['title'])}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
    max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333;
    line-height: 1.7;
  }}
  h1 {{ font-size: 24px; margin-bottom: 6px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 32px; border-bottom: 1px solid #eee; padding-bottom: 16px; }}
  a {{ color: #2d6cdf; }}
  ul {{ padding-left: 1.5em; }}
  hr {{ border: none; border-top: 1px solid #eee; margin: 24px 0; }}
</style>
</head>
<body>
<h1>{html.escape(post['title'])}</h1>
<p class="meta">발행일: {post_date} &nbsp;|&nbsp; 태그: {html.escape(tags_str)}</p>
{post['html_body']}
</body>
</html>"""


def _build_posting_guide(post: dict, post_date: str, has_image: bool) -> str:
    tags_str = ", ".join(post.get("tags", []))
    img_step = (
        "  → header_image.jpg 를 대표 이미지로 업로드\n"
        if has_image else
        "  → 이미지 없음 (직접 준비하거나 생략)\n"
    )
    return f"""티스토리 수동 등록 가이드 ({post_date})
{"=" * 52}

[1단계] 티스토리 글쓰기 화면 열기
  https://www.tistory.com → 로그인 → 글쓰기

[2단계] 제목 입력
  {post['title']}

[3단계] 본문 HTML 붙여넣기
  1. 에디터 상단 'HTML' 버튼 클릭 (또는 '>' 토글 아이콘)
  2. tistory_body.html 파일을 텍스트 에디터(VS Code 등)로 열기
  3. 전체 선택(Ctrl+A) → 복사(Ctrl+C)
  4. 티스토리 HTML 에디터 창에 붙여넣기(Ctrl+V)
  5. '기본' 또는 '편집' 모드로 전환해 미리보기 확인

  💡 미리보기: preview.html 파일을 브라우저에서 열면 발행 전 확인 가능

[4단계] 대표 이미지
{img_step}
[5단계] 카테고리 선택
  {TISTORY_CATEGORY}

[6단계] 태그 입력
  {tags_str}

[7단계] 발행
  '완료' → '발행' 클릭

{"=" * 52}
"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="슬랙 KOL 브리핑 → 로컬 저장 (티스토리 수동 등록용)"
    )
    ap.add_argument("--from-slack", action="store_true", help="슬랙에서 최신 브리핑 읽기")
    ap.add_argument("--input", help="브리핑 텍스트 파일 (테스트용)")
    ap.add_argument("--date", help="발행일 YYYY-MM-DD (생략 시 오늘)")
    args = ap.parse_args()

    if args.from_slack:
        print("[입력] 슬랙에서 최신 브리핑 읽는 중...", file=sys.stderr)
        briefing = fetch_briefing_from_slack()
    elif args.input:
        briefing = Path(args.input).read_text(encoding="utf-8")
    else:
        briefing = sys.stdin.read()
    if not briefing.strip():
        sys.exit("입력 브리핑이 비어 있습니다.")

    post_date = args.date or datetime.date.today().isoformat()

    print("[1/3] 헤더 이미지 다운로드 중...", file=sys.stderr)
    download_header_image(briefing, post_date)
    norm = _normalize_slack(briefing)
    lead_url_m = re.search(r"https?://t\.me/\S+", norm)
    image_bytes = load_header_image(
        post_date, lead_url_m.group(0).rstrip(").,") if lead_url_m else None
    )
    if image_bytes is None:
        print("  (헤더 이미지 없음 — 이미지 없이 진행)", file=sys.stderr)

    print("[2/3] 원문 포맷 변환 + 해시태그...", file=sys.stderr)
    post = format_briefing(briefing, post_date)

    print("[3/3] 로컬 파일 저장 중...", file=sys.stderr)
    day_dir = save_output(post, post_date, image_bytes)

    print(f"\n저장 완료: {day_dir}/")
    print(f"  제목:    {post['title']}")
    print(f"  태그:    {' '.join('#' + t for t in post['tags'])}")
    print(f"  이미지:  {'있음 (' + str(len(image_bytes)//1024) + 'KB)' if image_bytes else '없음'}")
    print(f"\n  파일 목록:")
    for f in sorted(day_dir.iterdir()):
        size = f.stat().st_size
        size_str = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
        print(f"    {f.name:<25} {size_str}")
    print(f"\n  → posting_guide.txt 를 참고해 티스토리에 수동 등록하세요.")


if __name__ == "__main__":
    main()
