demo:
	docker compose up -d --build
	docker compose exec api alembic upgrade head
	docker compose exec api python3 -m metering.demo