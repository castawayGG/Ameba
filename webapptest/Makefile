# =============================================================================
# Makefile — Ameba (Telegram Panel) helper targets
#
# Prerequisites: Docker Engine ≥ 24 with Compose plugin.
#
# Usage:
#   make start    – build images and start all services (local dev, HTTP)
#   make stop     – stop and remove containers
#   make restart  – stop, rebuild and start
#   make logs     – follow logs for all services
#   make status   – show container status
#   make shell    – open a bash shell inside the web container
#   make migrate  – run Alembic migrations inside the web container
# =============================================================================

.PHONY: start stop restart logs status shell migrate

start:
	@bash start.sh start

stop:
	@bash start.sh stop

restart:
	@bash start.sh restart

logs:
	@bash start.sh logs

status:
	@bash start.sh status

shell:
	docker compose exec web bash

migrate:
	docker compose exec web alembic upgrade head
