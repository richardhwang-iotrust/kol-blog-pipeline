#!/usr/bin/env bash
# 매일 아침 10시 자동 실행 스크립트 (cron 에서 호출)
# crontab 등록:  crontab -e  →  0 10 * * * /Users/iotairdrop/Documents/GitHub/kol-blog-pipeline/run_daily.sh

set -euo pipefail

PROJ="/Users/iotairdrop/Documents/GitHub/kol-blog-pipeline"
PYTHON="$PROJ/.venv/bin/python3"
LOG="$PROJ/logs/run_$(date +%Y%m%d).log"

mkdir -p "$PROJ/logs"

# cron 은 PATH 가 좁으므로 명시적으로 지정
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 시작 ===" | tee -a "$LOG"

# .env 로드 (cron 은 환경변수를 상속하지 않음)
if [ -f "$PROJ/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$PROJ/.env"
    set +o allexport
fi

cd "$PROJ"
"$PYTHON" pipeline.py --from-slack 2>&1 | tee -a "$LOG"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 완료 ===" | tee -a "$LOG"
echo ""
echo "저장 위치: $PROJ/output/$(date +%Y-%m-%d)/"
