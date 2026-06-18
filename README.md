# kol-blog-pipeline

슬랙 KOL 브리핑을 읽어 **티스토리 수동 등록용 파일**을 로컬에 저장하는 파이프라인입니다.

티스토리 자동 발행(Playwright)은 세션 만료·캡챠 문제로 신뢰성이 낮아 수동 등록 방식으로 전환했습니다.

## 산출물

실행 시 `output/YYYY-MM-DD/` 폴더에 아래 파일을 저장합니다.

| 파일 | 용도 |
|------|------|
| `tistory_body.html` | 티스토리 HTML 에디터에 붙여넣을 본문 |
| `preview.html` | 브라우저 미리보기용 전체 페이지 |
| `meta.json` | 제목·태그·요약 |
| `header_image.jpg` | 대표 이미지 (텔레그램에서 자동 다운로드) |
| `linkedin_draft.txt` | 링크드인 게시 초안 |
| `posting_guide.txt` | 수동 등록 순서 안내 |

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dotenv pillow
cp .env.example .env   # 값 채우기
```

## 사용법

```bash
# 슬랙에서 오늘 브리핑 읽어 처리
python pipeline.py --from-slack

# 파일에서 읽기 (테스트용)
python pipeline.py --input briefing.txt

# 날짜 지정
python pipeline.py --from-slack --date 2026-06-18
```

## 티스토리 등록 방법

1. [티스토리 글쓰기](https://www.tistory.com) 열기
2. 제목: `meta.json`의 `title` 복사·붙여넣기
3. 에디터 상단 **HTML** 버튼 클릭
4. `tistory_body.html` 내용 전체 선택(Ctrl+A) → 복사 → 붙여넣기
5. 기본 모드로 전환 후 내용 확인
6. `header_image.jpg`를 대표 이미지로 업로드
7. 태그·카테고리 입력 → **발행**

> 자세한 순서는 `output/YYYY-MM-DD/posting_guide.txt` 참고

## 자동 실행 (cron)

```bash
chmod +x run_daily.sh
# crontab -e
# 0 10 * * * /Users/iotairdrop/Documents/GitHub/kol-blog-pipeline/run_daily.sh
```

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `SLACK_BOT_TOKEN` | ✅ | Slack Bot 토큰 (xoxb-...) |
| `SLACK_CHANNEL_ID` | ✅ | 브리핑 채널 ID |
| `MEDIA_DIR` | | 이미지 캐시 폴더 (기본: `./media`) |
| `TELEGRAM_BOT_TOKEN` | | 이미지 다운로드 성공률 향상 |
| `SLACK_DM_USER_ID` | | 링크드인 초안을 DM으로 받을 사용자 ID |
| `TISTORY_BLOG_NAME` | | 링크드인 초안 URL용 블로그명 |
