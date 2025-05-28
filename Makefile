.PHONY: test lint security integration-test deploy health-check install-dev clean

# Default target
all: test lint security

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov pytest-mock black isort flake8 bandit safety pre-commit
	pre-commit install

# Run unit tests
test:
	@echo "🧪 Running GPU compatibility unit tests..."
	python -m pytest test_vertex_gpu_compatibility.py::TestGPUCompatibilityMapping -v --tb=short

# Run tests with coverage
test-coverage:
	@echo "🧪 Running tests with coverage..."
	python -m pytest test_vertex_gpu_compatibility.py::TestGPUCompatibilityMapping --cov=vertex_gpu_service --cov-report=term-missing --cov-report=html

# Run linting
lint:
	@echo "🔍 Running code formatting and linting..."
	black --check --diff .
	isort --check-only --diff .
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Fix formatting issues
format:
	@echo "🔧 Fixing code formatting..."
	black .
	isort .

# Run security checks
security:
	@echo "🔒 Running security checks..."
	bandit -r . -ll
	safety check

# Run integration tests (requires GCP credentials)
integration-test:
	@echo "🌐 Running integration tests..."
	RUN_INTEGRATION_TESTS=1 python -m pytest test_vertex_gpu_compatibility.py::TestGPUCompatibilityIntegration -v

# Run all tests (unit + integration)
test-all: test integration-test

# Deploy to Cloud Run
deploy:
	@echo "🚀 Deploying to Cloud Run..."
	gcloud run deploy av-app --source . --region us-central1 --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 3600 --concurrency 1 --max-instances 1

# Run health check
health-check:
	@echo "🏥 Running health check..."
	curl -f https://av-app-939407899550.us-central1.run.app/health/machine-types | jq '.'

# Test video generation
test-video:
	@echo "🎬 Testing video generation..."
	curl -X POST https://av-app-939407899550.us-central1.run.app/generate -H "Content-Type: application/json" -d '{"story": "Test GPU compatibility from Makefile"}'

# Check video status
status:
	@echo "📊 Checking video generation status..."
	curl -s https://av-app-939407899550.us-central1.run.app/status | jq '.'

# Full CI pipeline locally
ci: test lint security
	@echo "✅ Local CI pipeline completed successfully!"

# Clean up generated files
clean:
	@echo "🧹 Cleaning up..."
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -f .coverage
	rm -f coverage.xml
	rm -f bandit-report.json
	rm -f safety-report.json

# Setup Cloud Build trigger
setup-cloudbuild:
	@echo "⚙️ Setting up Cloud Build trigger..."
	gcloud builds triggers create github \
		--repo-name=AutoVideo.v1 \
		--repo-owner=rezearcher \
		--branch-pattern="^main$$" \
		--build-config=cloudbuild.yaml \
		--description="Auto Video Generator CI/CD Pipeline"

# Help
help:
	@echo "Available commands:"
	@echo "  install-dev     - Install development dependencies"
	@echo "  test           - Run unit tests"
	@echo "  test-coverage  - Run tests with coverage report"
	@echo "  lint           - Run code linting"
	@echo "  format         - Fix code formatting"
	@echo "  security       - Run security checks"
	@echo "  integration-test - Run integration tests"
	@echo "  test-all       - Run all tests"
	@echo "  deploy         - Deploy to Cloud Run"
	@echo "  health-check   - Run health check"
	@echo "  test-video     - Test video generation"
	@echo "  status         - Check video generation status"
	@echo "  ci             - Run full CI pipeline locally"
	@echo "  clean          - Clean up generated files"
	@echo "  setup-cloudbuild - Setup Cloud Build trigger"
	@echo "  help           - Show this help message" 