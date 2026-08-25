#!/usr/bin/env bash
# Runs ClickHouse and Postgres from local binaries, with all state under .local/.
# Used when Docker is unavailable; docker-compose.yml is the containerized equivalent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$ROOT/.local"
CH_BIN="${CLICKHOUSE_BIN:-$LOCAL/bin/clickhouse}"
PG_BIN="${PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
CH_HTTP_PORT="${CLICKHOUSE_PORT:-27105}"
PG_PORT="${POSTGRES_PORT:-5505}"
PGDATA="$LOCAL/pgdata"

# Pinned LTS release; digests are the SHA-256 values GitHub publishes for each release asset.
CH_VERSION="26.8.17.4"
CH_RELEASE="https://github.com/ClickHouse/ClickHouse/releases/download/v$CH_VERSION-lts"

sha256_of() {
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

ensure_clickhouse() {
  [[ -x "$CH_BIN" ]] && return
  local asset digest download
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) asset="clickhouse-macos-aarch64"; digest="0eed531549cecc687b2ab00a57c2432eefd4a8166266d051733b64c24402668d" ;;
    Darwin-x86_64) asset="clickhouse-macos"; digest="c6e586eef669915c2d35a427f4d5e05eedb7d936df2a4471d3b1152eca352388" ;;
    Linux-aarch64) asset="clickhouse-common-static-$CH_VERSION-arm64.tgz"; digest="f67dd4c2ae38b7cba3ca713d3da7e22d49038a3be32798f5ff4ac7424ea14971" ;;
    Linux-x86_64) asset="clickhouse-common-static-$CH_VERSION-amd64.tgz"; digest="c06e8573d513d03e0e44f7b66060f8b0bc35d8aa2eb1996c1fcb102160d9b93c" ;;
    *) echo "no pinned clickhouse build for $(uname -sm); set CLICKHOUSE_BIN" >&2; exit 1 ;;
  esac
  mkdir -p "$LOCAL/bin"
  download="$LOCAL/bin/$asset.download"
  echo "downloading clickhouse $CH_VERSION ($asset)"
  curl -sSfL -o "$download" "$CH_RELEASE/$asset"
  if [[ "$(sha256_of "$download")" != "$digest" ]]; then
    rm -f "$download"
    echo "checksum mismatch for $asset; refusing to run it" >&2
    exit 1
  fi
  if [[ "$asset" == *.tgz ]]; then
    tar -xzf "$download" -C "$LOCAL/bin" --strip-components=3 "clickhouse-common-static-$CH_VERSION/usr/bin/clickhouse"
    rm -f "$download"
  else
    mv "$download" "$CH_BIN"
  fi
  chmod +x "$CH_BIN"
}

start_clickhouse() {
  ensure_clickhouse
  mkdir -p "$LOCAL/clickhouse"/{log,data,tmp,user_files,format_schemas}
  sed -e "s#{{LOCAL}}#$LOCAL#g" -e "s#{{HTTP_PORT}}#$CH_HTTP_PORT#g" \
    "$ROOT/infra/clickhouse/local-config.xml" > "$LOCAL/clickhouse/config.xml"
  if curl -sf "http://127.0.0.1:$CH_HTTP_PORT/ping" >/dev/null 2>&1; then
    echo "clickhouse already running on :$CH_HTTP_PORT"
    return
  fi
  # exec replaces the subshell and every standard stream is redirected, so nothing keeps the
  # caller's stdout open; `make services | tail` returns as soon as the script does.
  (cd "$LOCAL/clickhouse" && exec nohup "$CH_BIN" server --config-file="$LOCAL/clickhouse/config.xml" \
    --pid-file="$LOCAL/clickhouse/clickhouse.pid" </dev/null >"$LOCAL/clickhouse/log/stdout.log" 2>&1) &
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$CH_HTTP_PORT/ping" >/dev/null 2>&1 && { echo "clickhouse up on :$CH_HTTP_PORT"; return; }
    sleep 0.5
  done
  echo "clickhouse failed to start; see $LOCAL/clickhouse/log" >&2
  exit 1
}

start_postgres() {
  if [[ ! -d "$PGDATA" ]]; then
    "$PG_BIN/initdb" -D "$PGDATA" -U tracebench --auth=trust >/dev/null
  fi
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PG_PORT" >/dev/null 2>&1; then
    echo "postgres already running on :$PG_PORT"
  else
    "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$LOCAL/postgres.log" -o "-p $PG_PORT -k /tmp -c listen_addresses=127.0.0.1" -w start \
      </dev/null >/dev/null 2>&1
    echo "postgres up on :$PG_PORT"
  fi
  for db in tracebench tracebench_test; do
    "$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U tracebench -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
      || "$PG_BIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U tracebench "$db"
  done
}

stop_all() {
  if [[ -f "$LOCAL/clickhouse/clickhouse.pid" ]]; then
    kill "$(cat "$LOCAL/clickhouse/clickhouse.pid")" 2>/dev/null || true
    rm -f "$LOCAL/clickhouse/clickhouse.pid"
    echo "clickhouse stopped"
  fi
  if [[ -d "$PGDATA" ]]; then
    "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast stop >/dev/null 2>&1 && echo "postgres stopped" || true
  fi
}

case "${1:-start}" in
  start) start_clickhouse; start_postgres ;;
  stop) stop_all ;;
  *) echo "usage: $0 [start|stop]" >&2; exit 2 ;;
esac
