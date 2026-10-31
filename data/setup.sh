#!/usr/bin/env bash
# Dựng lại toàn bộ database local của Growth Agents bằng một lệnh.
#
#   bash data/setup.sh              # cài môi trường, tạo DB nếu chưa có, kiểm tra
#   bash data/setup.sh --reset      # sao lưu DB cũ rồi dựng lại từ đầu
#   bash data/setup.sh --reset --proof --serve
#
# Chạy được từ bất kỳ thư mục nào. Không cần OpenAI key.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOME_DIR="$SCRIPT_DIR/runtime"
RESET=0
PROOF=0
SERVE=0
TEST=0
REGEN=0
PORT=8001
HOST=127.0.0.1

usage() {
  cat <<'EOF'
Cách dùng: bash data/setup.sh [tuỳ chọn]

  --reset            Sao lưu growth.db hiện có vào <home>/backups/ rồi xoá runtime và dựng lại
                     (không có --reset: giữ dữ liệu cũ; nếu schema cũ thì tự sao lưu rồi nâng)
  --proof            Chạy thử 7 ngày, bộ nhớ bật và tắt, xuất <home>/exports/proof.json
  --test             Chạy pytest của phần data (không gọi API trả phí)
  --serve            Sau khi xong, chạy API ở http://HOST:PORT
  --port N           Cổng cho --serve (mặc định 8001)
  --host H           Host cho --serve (mặc định 127.0.0.1; dùng 0.0.0.0 để mở trong LAN)
  --home DIR         Thư mục runtime (mặc định data/runtime)
  --regen-datasets   Sinh lại data/datasets/ từ code (sẽ đổi file đã commit nếu code seed đổi)
  -h, --help         Xem hướng dẫn này
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --reset) RESET=1 ;;
    --proof) PROOF=1 ;;
    --test) TEST=1 ;;
    --serve) SERVE=1 ;;
    --regen-datasets) REGEN=1 ;;
    --port) PORT="${2:?Thiếu giá trị cho --port}"; shift ;;
    --host) HOST="${2:?Thiếu giá trị cho --host}"; shift ;;
    --home) HOME_DIR="${2:?Thiếu giá trị cho --home}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Tuỳ chọn không hợp lệ: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nLỗi: %s\n' "$*" >&2; exit 1; }

# Đường dẫn tuyệt đối để CLI và API cùng nhìn một database.
mkdir -p "$HOME_DIR"
HOME_DIR="$(cd "$HOME_DIR" && pwd)"
cd "$ROOT"

command -v uv >/dev/null 2>&1 || fail "Chưa cài uv. Cài bằng: curl -LsSf https://astral.sh/uv/install.sh | sh  (hoặc: brew install uv), rồi mở terminal mới."

gd() { uv run --project data growth-data --home "$HOME_DIR" "$@"; }

step "1/5 Cài môi trường Python 3.11 và dependency theo data/uv.lock (data/.venv)"
uv sync --project data --python 3.11 --locked

backup_db() {
  mkdir -p "$HOME_DIR/backups"
  BACKUP="$HOME_DIR/backups/growth-$(date +%Y%m%d-%H%M%S)-v$1.db"
  gd backup-db --output "$BACKUP" >/dev/null
  echo "Đã sao lưu DB cũ (schema v$1): $BACKUP"
}

if [ -f "$HOME_DIR/growth.db" ]; then
  # Mở DB là service tự nâng schema; sao lưu trước khi nâng hoặc trước khi xoá.
  CURRENT="$(uv run --project data python -I -c 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("PRAGMA user_version").fetchone()[0])' "$HOME_DIR/growth.db")"
  LATEST="$(find "$SCRIPT_DIR/growth_data/migrations" -name '[0-9]*.sql' | wc -l | tr -d ' ')"
  if [ "$RESET" -eq 1 ] || [ "$CURRENT" -lt "$LATEST" ]; then
    backup_db "$CURRENT"
  fi
  if [ "$RESET" -eq 0 ] && [ "$CURRENT" -lt "$LATEST" ]; then
    echo "DB sẽ được nâng từ schema v$CURRENT lên v$LATEST; dữ liệu cũ được giữ."
  fi
fi

if [ "$RESET" -eq 1 ]; then
  step "Đặt lại runtime: $HOME_DIR"
  # Token cũ gắn với DB cũ nên xoá cùng lúc; giữ lại thư mục backups.
  rm -f "$HOME_DIR"/growth.db "$HOME_DIR"/growth.db-wal "$HOME_DIR"/growth.db-shm \
        "$HOME_DIR"/dev-credentials.json "$HOME_DIR"/cursor.secret
  rm -rf "$HOME_DIR"/objects "$HOME_DIR"/exports
fi

if [ "$REGEN" -eq 1 ]; then
  step "Sinh lại data/datasets/ từ code"
  uv run --project data growth-data --home "$HOME_DIR" seed
fi

step "2/5 Tạo schema, dữ liệu dùng chung và token dev"
gd init-db

step "3/5 Kiểm tra toàn vẹn dữ liệu"
gd validate-data

if [ "$PROOF" -eq 1 ]; then
  step "4/5 Chạy kịch bản 7 ngày, bộ nhớ bật và tắt"
  gd run-scenario --days 7 --seed 42 --compare
else
  step "4/5 Bỏ qua chạy kịch bản (thêm --proof nếu cần proof.json)"
fi

if [ "$TEST" -eq 1 ]; then
  step "5/5 Chạy test phần data và ghi báo cáo nghiệm thu"
  gd verify-demo --report "$HOME_DIR/gate-a-report.json"
  echo "Báo cáo: $HOME_DIR/gate-a-report.json"
else
  step "5/5 Bỏ qua test (thêm --test để chạy)"
fi

cat <<EOF

Xong. Database: $HOME_DIR/growth.db
Token dev (không commit, không đưa vào frontend): $HOME_DIR/dev-credentials.json

Chạy API:
  uv run --project data growth-data --home "$HOME_DIR" serve --port $PORT
  Swagger: http://127.0.0.1:$PORT/docs
Run demo của người bán được tạo tự động ở lần gọi GET /api/state đầu tiên.
EOF

if [ "$SERVE" -eq 1 ]; then
  step "Chạy API ở http://$HOST:$PORT (Ctrl+C để dừng)"
  exec uv run --project data growth-data --home "$HOME_DIR" serve --host "$HOST" --port "$PORT"
fi
