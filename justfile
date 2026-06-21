# Justfile for Taskbench development

# Default recipe - show available commands
default:
    @just --list

# Run linting, type checking, and tests (excludes live tests)
check:
    @echo "Running ruff linting..."
    uv run ruff check
    @echo "Running format check..."
    uv run ruff format --check
    @echo "Running type checking..."
    uv run ty check
    @echo "Running tests..."
    uv run pytest --cov=taskbench --cov-report=xml --cov-report=term-missing

# Run all checks including live integration tests (requires CLICKUP_API_KEY)
check-local:
    @echo "Running ruff linting..."
    uv run ruff check
    @echo "Running format check..."
    uv run ruff format --check
    @echo "Running type checking..."
    uv run ty check
    @echo "Running unit and integration tests..."
    uv run pytest tests/unit tests/integration --cov=taskbench --cov-report=term-missing
    @echo "Running live integration tests..."
    uv run pytest tests/live -v --no-cov

# Audit dependencies for known vulnerabilities (issue #67 P3).
# Runs pip-audit via `uv tool run` so it isn't a project dep — it's a
# security tool, not a runtime requirement. `--path .venv` targets the
# project environment, otherwise pip-audit ends up auditing its own
# transitive deps in the isolated tool env.
audit:
    @echo "Auditing dependencies for known vulnerabilities..."
    uv tool run pip-audit --strict --path .venv

# Fix linting and formatting issues
fix:
    @echo "Fixing linting issues..."
    uv run ruff check --fix
    @echo "Formatting code..."
    uv run ruff format

# Fix and then check (quick iteration)
fc: fix check

# Fix and then check-local (full local validation)
fc-local: fix check-local

# Run tests only (excludes live tests)
test:
    uv run pytest --cov=taskbench --cov-report=xml --cov-report=term-missing

# Run live integration tests only (requires CLICKUP_API_KEY)
test-live:
    @echo "Running live integration tests..."
    @echo "Note: Requires CLICKUP_API_KEY environment variable or .env file"
    uv run pytest tests/live -v --no-cov

# Run all tests including live tests
test-all:
    @echo "Running all tests..."
    uv run pytest tests/unit tests/integration --cov=taskbench --cov-report=term-missing
    uv run pytest tests/live -v --no-cov

# Install dependencies
install:
    uv sync --dev

# Run specific test file
test-file FILE:
    uv run pytest {{FILE}} -v

# Run tests with specific pattern
test-pattern PATTERN:
    uv run pytest -k "{{PATTERN}}" -v

# Clean up generated files
clean:
    rm -rf .pytest_cache
    rm -rf .coverage
    rm -rf coverage.xml
    rm -rf htmlcov
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Build the package
build:
    uv build

# Run the CLI locally
cli *ARGS:
    uv run taskbench {{ARGS}}

# Type checking
typecheck:
    uv run ty check

# Full development setup
setup: install
    @echo "Development environment ready!"
    @echo "Run 'just check' to validate your setup"
    @echo "Run 'just check-local' to run all checks including live tests"
