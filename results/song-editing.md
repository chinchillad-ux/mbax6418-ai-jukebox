# Song editing verification

## Using the feature

In **My Library**, choose a saved song (or click its cover), then use **Edit selected song**:

- **Save Song Title** persists a trimmed title (1–200 characters), preserving the track ID, audio, lyrics, and artwork. Library and DJ selectors refresh. An unchanged title is a no-op.
- A changed title clears that track's stored DJ commentary/audio reference. This browser's DJ preview and playlist stop and clear; generate a new introduction before rebuilding the set. Existing audio files are not deleted.
- Edit **Cover description** (1–2000 characters) and choose **Regenerate Album Cover**. This calls the existing configured FLUX image-generation service with musical style, mood, and the requested visual direction. It does not automatically insert the song title or lyrics into this custom prompt. There is no image upload. The original default generation flow (without a custom description) is unchanged.
- The previous cover remains saved and displayed if generation or metadata persistence fails. The failed description remains in the editor for retry; only successful descriptions persist across reloads. Both existing and missing covers are supported.

## Automated evidence

Run with Python 3.11 and ffmpeg on PATH:

```bash
PATH="$HOME/.local/bin:$PATH" GRADIO_ANALYTICS_ENABLED=False .venv/bin/python -m pytest -q
```

After the lettering fix: **197 passed, 11 upstream deprecation warnings**. Before the production change, the two parameterized payload regressions failed because original/changed titles were present in the outgoing custom FLUX prompt. They now assert that neither title nor lyrics is inserted, while style, mood, visual direction, and no-lettering instructions remain. Existing default-prompt coverage passes.

The first full-suite run exposed an obsolete runtime-test assertion requiring the renamed title in the custom image prompt. That assertion was changed to require its absence (and lyrics' absence); persisted title and editor reload assertions remain. The subsequent full suite passed.

`tests/test_song_editing_runtime.py` starts the real Gradio HTTP server and calls its endpoints through `gradio_client`. Only FLUX settings/HTTP transport are mocked with dummy configuration and valid generated PNG fixtures. It exercises editor load, rename, successful replacement, simulated outage retaining the replacement, and reload. The server is closed afterward.

Coverage also includes failed atomic writes, unchanged audio/lyrics/files, duplicate titles/stable IDs, legacy records, invalid input, concurrent rename preservation, and DJ invalidation. Deprecation warnings concern Gradio theme/CSS constructor parameters and the HTTP 422 constant. `git diff --check` passes. Bundled sample assets remain unchanged.

## Actual FLUX evidence — October 27, 2026 UTC

Executed `/Users/dora/.hermes/cache/scratch/verify_song_editing_flux.py` using the existing stored credential handling, without printing credentials. It uses real UI callbacks and the FLUX service on port 9006 with model `black-forest-labs/FLUX.2-klein-4B`, in an isolated scratch library, not the bundled sample library.

Exactly **two successful live generations are documented across this investigation: one before the fix and one after**. No additional post-fix retry was necessary.

- **Before fix**, report timestamp `2026-10-27T02:47:25.166626+00:00`: the PNG had a large song title and multiple lines of mangled lyric-like lettering, confirmed by visual inspection. The custom description was appended to a default prompt containing the full title and lyrics despite its no-lettering instructions.
  - Image: `/Users/dora/.hermes/cache/scratch/song-editing-live-flux/data/covers/dc85a256879c4e1ea793ea88cfcb52e1.png`
  - Original report preserved at `/Users/dora/.hermes/cache/scratch/song-editing-live-flux/report-before-fix.json`.
- **After fix**, report timestamp `2026-10-27T02:52:46.662081+00:00`: valid decoded **1024×1024 PNG**. Visual inspection shows the requested painterly amber sunrise and wildflower meadow, with **no visible lettering, title, lyrics, logos, or watermark in this image**.
  - Image: `/Users/dora/.hermes/cache/scratch/song-editing-live-flux/data/covers/2e15fc5aced54b59853386705bc1deef.png`
  - Report: `/Users/dora/.hermes/cache/scratch/song-editing-live-flux/report.json` (its `live_calls: 1` describes this single run, not the cumulative total).

Both calls used this description:

> A warm copper and amber sunrise over a meadow of wildflowers, hopeful indie pop mood, painterly illustration. No lettering, logos, or words.

The post-fix script verified persisted changed title `Copper Morning Test`, persisted description and replacement path, unchanged audio path/hash and lyrics, cleared DJ audio reference, editor reload, and preservation of the new image/path/hash after rejecting a blank description without a further service call. Service-outage and persistence-failure preservation are tested with injected failures, not a deliberate live outage.

## Scope and limitations

One successful post-fix visual sample is evidence for this scenario, not a guarantee that a stochastic image model will never render text. User-provided descriptions/style/mood can themselves contain text; the fix avoids automatically supplying title/lyrics rather than sanitizing all metadata. The default no-custom-description flow intentionally retains its original title/lyric prompt and is not claimed to solve lettering there.

The live FLUX run above was not a visual browser or manual playback test and preceded integration of PR #15. The later verification below includes PR #15 and real browser interaction, without further live AI calls. JSON write coordination is single-process, as in the existing library. Other open browsers can retain already-loaded media until refreshed. Superseded artwork and DJ files are retained rather than deleted, and a generated file may remain unused if metadata saving fails. Scratch evidence is local and subject to cache pruning; no generated images or credentials were added to the repository.

## Browser regression fixes — October 27, 2026 UTC

Tested implementation: `44bb677a2ecd575e3f48e2b764734b70ebb2c6bd`, including current main `00a8c3a4a47d0da074d305adf2f2bc2b9ad3c839` through integration commit `9130ba6b7236ffa724e04a9122d786726d04400c`. PR #15's endpoint-example correction is included. Original PR #16 head was `2d8cbc874c60c49f5ae0d8e716006588b8778d4b`.

Two confirmed browser defects were fixed:

- Slow regeneration wrote its image directly into the editor even after selection changed. Both regeneration and missing-cover retry now store an identity-tagged result in separate session state. A nonqueued follow-up reads the browser's current selection, applies artwork/status only for the matching song, and reads its latest persisted cover. Successful operations refresh dropdown labels without choosing the initiating song. Neither completion path outputs the editable title or description. The two generation actions share a concurrency group, including queued retry clicks.
- Rename now explicitly updates **Now selected**; refreshing choices with the same stable ID alone does not trigger Gradio's selection-change callback.

### Red → green and automated checks

Before changing the corresponding production code, the rename regression failed on the missing selected-title output, and both slow-event wiring regressions failed because generation directly targeted visible components. Follow-up tests cover selected identity, cleared selection, unchanged draft fields, failure skips, choice refresh, and nonqueued result presentation. The HTTP runtime test now explicitly calls generation and its presentation event in the same client session, matching the browser's chained events; `/regenerate_cover` and `/retry_cover` now store state rather than returning a visible preview directly.

`uv sync --frozen --extra dev` succeeded. The full suite at the tested implementation passed: **204 tests, 17 upstream deprecation warnings**. The warning categories are unchanged (Gradio theme/CSS and HTTP 422); additional app constructions and HTTP calls increase their count. No failing tests were ignored.

The browser harness was also run against the earlier combined-main/PR tree: `--case switch` failed with Song B's red image in Song A's editor; `--case rename` failed with `Now selected: Song B` after renaming to `Renamed B`. These baseline runs establish that the browser assertions detect the original defects, rather than merely exercising controls.

### Actual Chrome scenarios

Reproducible standalone check (Playwright is an optional verification dependency, not an app dependency):

```bash
uv run --with playwright python scripts/verify_song_editing_browser.py \
  --evidence /absolute/scratch/evidence-directory \
  --chrome /absolute/path/to/chrome
```

The harness launches an isolated temporary headless Chrome profile and the real local Gradio app. It never opens the user's locked Chrome profile. Only FLUX settings/transport are replaced with dummy configuration, valid colored PNGs, and a controllable delay/outage. It uses actual dropdown, textbox, rename, regenerate, and retry clicks—not just `gradio_client` calls.

All **nine scenarios passed twice** on the final implementation:

1. Rename updates gallery, selector, editor, persistence, DJ invalidation, and **Now selected**.
2. Regenerate B, switch to A during the delayed transport: A's blue cover and unsaved draft remain; B alone persists the new red cover.
3. Failed generation preserves the old image and a description edited while the request was active.
4. Retry missing cover C, then switch to A: A's editor and selected-song status stay correct.
5. Reselect C after retry: its new artwork and refreshed choice label are correct.
6. Queue retry D behind delayed regeneration B, then select A: neither completion replaces A's image; B and D persist correctly.
7. Switch B → A → B during generation: B displays its latest saved image without replacing its newer unsaved draft.
8. Switch to A before B's outage completes: A's image and draft remain, without B's failure message being applied.
9. Reload and reselect B: the renamed title, successfully saved description, and image persist.

Each full browser run made **seven synthetic transport requests, zero live AI calls**. Audio paths, lyrics, and all six original synthetic media files remained unchanged. The test servers and browser instances closed afterward. Screenshots of the rename, switched-selection, and failure cases were visually inspected, in addition to DOM and persistence assertions.

Local evidence: `/Users/dora/.hermes/cache/scratch/pr16-fix-evidence/` contains `pytest.txt`, `checks.json`, the two baseline failure reports, and `browser-final/` plus `browser-repeat/` reports/screenshots. An initial harness attempt timed out on an exact accessible-label lookup that omitted Gradio's description help text; the harness locator was corrected before these successful runs. This was a test-selector issue, not a suppressed application failure.

### Diff checks and remaining gates

- All **11 bundled sample files** are byte-identical to current main; SHA-256 results are recorded locally.
- `git diff --check` and staged-diff checks passed. Added-line credential/private-key/token and dangerous-execution pattern scans found no hits; the changed code was also reviewed directly. This is a scoped change review, not a full-history security audit.
- Ruff still reports **31 pre-existing findings**. Compared by relative file, rule, and message against exact main using the same executable: **zero new lint findings**. The project is not globally lint-clean.
- GitHub reported no checks for this branch; there is no CI pass to claim.
- Independent teammate review and manual audible playback/non-overlap/paused-skip/end-event verification remain deferred to final review. Silent synthetic WAVs do not establish audible behavior. Existing single-process and other-browser media-cache limitations remain. This evidence does not authorize or claim a PR merge.
