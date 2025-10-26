# DonorIQ Backend Makefile

.PHONY: help install dev prod test clean docker-build docker-run migrate create-admin

help: ## Show this help message
	@echo "DonorIQ Backend - Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

dev: ## Start development server
	python run.py

prod: ## Start production server
	gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

test: ## Run tests
	python tests/test_api.py

test-pytest: ## Run tests with pytest
	pytest tests/

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create MESSAGE="description")
	alembic revision --autogenerate -m "$(MESSAGE)"

create-admin: ## Create admin user
	python scripts/create_admin_user.py

clean: ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/

docker-build: ## Build Docker image
	docker build -t donoriq-backend .

docker-run: ## Run Docker container
	docker run -p 8000:8000 --env-file .env donoriq-backend

docker-dev: ## Start development with Docker Compose
	docker-compose up -d

docker-stop: ## Stop Docker Compose services
	docker-compose down

logs: ## View application logs
	tail -f logs/app.log

setup: install migrate create-admin ## Complete setup (install, migrate, create admin)

check: ## Check code quality
	flake8 app/
	black --check app/

format: ## Format code
	black app/

lint: ## Lint code
	flake8 app/
