# Repository Guidelines

## Project Structure & Module Organization
Core code sits in `src/app`: `worker.py` orchestrates the async job loop, `database.py` manages the aiosqlite job/result store, and connectors under `bluesky`, `youtube`, `reddit`, `web`, and `llm` isolate service-specific logic. Integration specs mirror this layout in `tests/integration`, while generated artifacts land in `outputs/` and `chats/`. Repo root holds `pyproject.toml`, `uv.lock`, and the shared SQLite file `crawl_data.db`.

## Build, Test, and Development Commands
- `uv sync` installs Python 3.13 dependencies plus the `dev` extras defined in `pyproject.toml`.
- `uv run python -m app.worker` spins up the polling worker; set `PYTHONPATH=src` if invoking without uv.
- `uv run pytest` runs every test; add `-m "not integration"` for a fast unit-only pass.
- `uv run pytest tests/integration/test_worker_integration.py -m integration` validates the full crawl-to-database loop before publishing schema changes.

## Coding Style & Naming Conventions
Follow PEP 8/Black-style 4-space indentation, keep files importable under the `app.*` namespace, and type every function signature to match the existing Pydantic models. Async helpers should read as verbs with `_job` or `_task` suffix (`process_youtube_job`), and new workers belong in directories named after their queue key. No formatter is enforced yet, so run `uv run python -m pytest` before commits to catch syntax or lint regressions.

## Testing Guidelines
Pytest is configured with `pythonpath = "src"` and an `integration` marker; apply `@pytest.mark.integration` to anything touching external services or the live worker loop. Name test files `test_<feature>.py` alongside the code they validate, assert both success and failure payloads, and verify cache behavior by checking rows written to `crawl_data.db`. Keep fixtures lightweight, preferring inline builders over global state so async tests remain deterministic.

## Commit & Pull Request Guidelines
History shows Conventional Commits (`feat:`, `fix:`, etc.), so craft summaries that pair a scope with an action (`feat: add reddit connector cache`). Pull requests should describe the change, list the commands run (`uv run pytest`, worker dry runs), and link any issues or tickets. Add screenshots or log snippets if crawl output changed to spare reviewers from rerunning long jobs.

## Security & Configuration Tips
Load API secrets (OpenRouter, Bluesky, Reddit) via a local `.env`; `python-dotenv` loads it automatically, so never hard-code tokens. Be mindful that `crawl_data.db` and `outputs/` may contain user content—gitignore or redact before sharing. Crawler throttles and cache durations live in `worker.py`; adjust them there instead of embedding credentials or ad-hoc sleeps in connector modules.
