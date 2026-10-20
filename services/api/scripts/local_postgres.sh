#!/usr/bin/env bash
# Project-local PostgreSQL without Docker, using the Homebrew `postgres` binaries.
# Data lives in services/api/var/pgdata (gitignored). Usage: scripts/local_postgres.sh init|start|stop|status
set -euo pipefail
cd "$(dirname "$0")/.."
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
DATA=var/pgdata
LOG=var/postgres.log
PORT="${VEYRA_PG_PORT:-5432}"

case "${1:-}" in
  init)
    mkdir -p var
    initdb -D "$DATA" -U postgres --auth-local=trust --auth-host=scram-sha-256 -E UTF8 --locale=C
    pg_ctl -D "$DATA" -l "$LOG" -o "-p $PORT -k /tmp" -w start
    psql -h /tmp -p "$PORT" -U postgres -c "CREATE ROLE veyra LOGIN PASSWORD 'veyra';"
    psql -h /tmp -p "$PORT" -U postgres -c "CREATE DATABASE veyra OWNER veyra;"
    psql -h /tmp -p "$PORT" -U postgres -c "CREATE DATABASE veyra_test OWNER veyra;"
    ;;
  start) pg_ctl -D "$DATA" -l "$LOG" -o "-p $PORT -k /tmp" -w start ;;
  stop) pg_ctl -D "$DATA" -w stop ;;
  status) pg_ctl -D "$DATA" status ;;
  *) echo "usage: $0 init|start|stop|status" >&2; exit 2 ;;
esac
