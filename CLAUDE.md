# Audio Workstation

Self-hosted Moises alternative: yt-dlp downloads, Demucs splits, FastAPI + vanilla JS UI, one Docker container.

- Read `docs/architecture.md` first: layout, on-disk data model, API, job flow, where new features go.
- All user settings live in `.env`. A new setting gets a comment there and a row in the README table.
- No database and no frontend build. Keep it that way unless the user asks.
- Verify with `docker compose up -d --build` and `docker compose run --rm audio-workstation python -m tests.test_core`.
- Update README.md and docs/architecture.md with every behavior change.
