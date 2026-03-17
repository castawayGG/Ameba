#!/usr/bin/env bash
# =============================================================================
# start.sh — One-command launcher for Ameba (Telegram Panel)
#
# Usage:
#   ./start.sh          # build images and start all services (local dev)
#   ./start.sh stop     # stop and remove containers
#   ./start.sh restart  # stop, rebuild and start
#   ./start.sh logs     # follow service logs
#   ./start.sh status   # show container status
#
# Prerequisites:
#   - Docker Engine  ≥ 24
#   - Docker Compose plugin (docker compose) or docker-compose ≥ 1.29
#   - A populated .env file (copy from .env.example and fill in the values)
#
# Environment:  Local development (HTTP only, no SSL certificates required).
#               For production with HTTPS see nginx/default.conf and README.md.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── helpers ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # no colour

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── detect compose command ────────────────────────────────────────────────────
detect_compose() {
    if docker compose version &>/dev/null; then
        echo "docker compose"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    else
        die "Docker Compose is not installed. Install Docker Desktop or the Compose plugin."
    fi
}

COMPOSE=$(detect_compose)

# ── verify Docker is running ──────────────────────────────────────────────────
check_docker() {
    if ! docker info &>/dev/null; then
        die "Docker daemon is not running. Start Docker and try again."
    fi
}

# ── verify .env file ──────────────────────────────────────────────────────────
check_env() {
    if [[ ! -f ".env" ]]; then
        warn ".env file not found."
        if [[ -f ".env.example" ]]; then
            warn "Copying .env.example → .env  (please review and update the values!)"
            cp .env.example .env
        else
            die "Neither .env nor .env.example found. Create a .env file based on .env.example."
        fi
    fi

    # Check mandatory variables
    local missing=()
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
        local key="${line%%=*}"
        local val
        val=$(grep -E "^${key}=" .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'") || val=""
        if [[ -z "$val" || "$val" == "replace-with-a-long-random-string" || "$val" == "changeme" || "$val" == "0" ]]; then
            case "$key" in
                SECRET_KEY|POSTGRES_PASSWORD|ADMIN_PASSWORD_HASH|SESSION_ENCRYPTION_KEY)
                    missing+=("$key")
                    ;;
            esac
        fi
    done < .env.example

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "The following required variables are not configured in .env:"
        for v in "${missing[@]}"; do
            warn "  - $v"
        done
        warn "Edit .env and set all required values, then run ./start.sh again."
        warn "Refer to README.md for instructions on generating secrets."
        echo ""
        read -r -p "Continue anyway? [y/N] " confirm
        [[ "${confirm,,}" == "y" ]] || exit 1
    fi
}

# ── subcommands ───────────────────────────────────────────────────────────────
cmd_start() {
    check_docker
    check_env

    info "Building images and starting services…"
    $COMPOSE up --build -d

    info "Waiting for web service to become healthy…"
    local timeout=60
    local elapsed=0
    until $COMPOSE ps web 2>/dev/null | grep -q "healthy" || [[ $elapsed -ge $timeout ]]; do
        sleep 3
        elapsed=$((elapsed + 3))
        echo -n "."
    done
    echo ""

    if $COMPOSE ps web 2>/dev/null | grep -q "healthy"; then
        info "All services are up."
    else
        warn "Services started but web health check not yet passing (it may still be initialising)."
    fi

    info "Admin panel: http://localhost/admin"
    info "To follow logs run:  ./start.sh logs"
    info "To stop run:         ./start.sh stop"
}

cmd_stop() {
    check_docker
    info "Stopping services…"
    $COMPOSE down
    info "Done."
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_logs() {
    check_docker
    $COMPOSE logs -f --tail=100
}

cmd_status() {
    check_docker
    $COMPOSE ps
}

# ── main ─────────────────────────────────────────────────────────────────────
ACTION="${1:-start}"

case "$ACTION" in
    start)   cmd_start   ;;
    stop)    cmd_stop    ;;
    restart) cmd_restart ;;
    logs)    cmd_logs    ;;
    status)  cmd_status  ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status}"
        exit 1
        ;;
esac
