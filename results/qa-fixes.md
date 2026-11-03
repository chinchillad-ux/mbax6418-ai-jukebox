# QA findings fixes

Regression fixes for the five findings from the adversarial QA of merged main `aec6b98`.

Branch: `fix/professor-qa-findings`. Full suite after fixes: **250 passed, 32 warnings** (Gradio/dependency deprecation warnings; no failures).

## F1 — AI DJ would act on an auto-selected song (High)

The DJ picker no longer auto-selects a choice (`value=None` at build and on refresh), and `generate_dj_intro` rejects an empty selection with the existing friendly message instead of silently running the live Qwen+Chatterbox pipeline.

- Tests: `test_dj_intro_requires_selected_song`, `test_dj_song_dropdown_starts_unselected`, `test_refresh_dj_songs_keeps_no_selection`

## F2 — Newly generated songs missing from DJ picker (Medium)

Generating a song (or importing demo songs) now refreshes the AI DJ song and playlist pickers in the same click chain, so a song created in-session is immediately DJ-able.

- Tests: `test_generated_song_appears_in_dj_refresh`, `test_create_and_retry_refresh_the_dj_picker`, `test_demo_import_refreshes_the_dj_picker`

## F3 — Duplicate generation on rapid clicks (Medium)

A generation-wide non-blocking lock refuses a second Generate/Retry while one pipeline is in flight, returning "A song generation is already in progress" instead of spawning duplicate service requests. The lock is released on success and on failure.

- Tests: `test_second_generation_refused_while_in_flight`, `test_inflight_guard_releases_after_failure`

## F4 — Remove-song guard contradicted the visible selection (Low)

The library's saved-song picker no longer auto-selects the first track, so the "Select a saved song to remove" guard only fires when nothing was actually chosen.

- Test: `test_library_dropdown_starts_unselected`

## F5 — manifest.json 404 on every page load (Low)

The server now launches with Gradio's PWA mode enabled, which serves a valid `/manifest.json`; the frontend no longer logs a 404 on load. `python -m jukebox.app` remains the documented launch command.

- Test: `test_production_server_serves_manifest_json`
