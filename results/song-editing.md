# Song editing verification

## Using the feature

In **My Library**, choose a saved song (or click its cover), then use **Edit selected song**:

- **Save Song Title** persists a trimmed title (1–200 characters), preserving the track ID, audio, lyrics, and artwork. Library and DJ selectors refresh. An unchanged title is a no-op.
- A changed title clears that track's stored DJ commentary/audio reference. This browser's DJ preview and playlist stop and clear; generate a new introduction before rebuilding the set. Existing audio files are not deleted.
- Edit **Cover description** (1–2000 characters) and choose **Regenerate Album Cover**. This calls the existing configured FLUX image-generation service, with track context plus the requested visual direction. There is no image upload.
- The previous cover remains saved and displayed if generation or metadata persistence fails. The failed description remains in the editor for retry; only successful descriptions persist across reloads. Both existing and missing covers are supported.

## Automated evidence

Run with Python 3.11 and ffmpeg on PATH:

```bash
PATH="$HOME/.local/bin:$PATH" GRADIO_ANALYTICS_ENABLED=False .venv/bin/python -m pytest -q
```

The full suite passed twice consecutively: **196 passed** each run. The new tests cover persistence, unchanged song data and original files, duplicate titles/stable IDs, old-record compatibility, blank/oversized input, missing selections, failed generation, failed atomic writes, stale concurrent updates, DJ invalidation, editor wiring, and selector refresh.

`tests/test_song_editing_runtime.py` starts the real Gradio HTTP server and calls its endpoints through `gradio_client`. Only FLUX settings/HTTP transport are mocked with dummy configuration and valid generated PNG fixtures. It exercises editor load, rename, successful replacement, simulated outage retaining the replacement, and reload. The server is closed afterward.

The suite emits upstream deprecation warnings for Gradio's theme/CSS constructor parameters and HTTP 422 constant. No new Ruff findings were introduced (nine existing findings remain in touched baseline files); both new test files pass Ruff. `git diff --check` passes. Bundled sample assets remain unchanged.

## Scope and limitations

No live AI service calls or credentials were needed; this is not evidence of live FLUX availability or a visual browser/manual playback test. The existing endpoint configuration is unchanged; the separate cover-URL correction in PR #15 is not included here. JSON write coordination is single-process, as in the existing library. Other open browsers can retain already-loaded media until refreshed. Superseded artwork and DJ files are retained rather than deleted, and a generated file may remain unused if metadata saving fails.
