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

This was not a visual browser or manual playback test. The existing endpoint configuration is unchanged; the separate cover-URL correction in PR #15 is not included here. JSON write coordination is single-process, as in the existing library. Other open browsers can retain already-loaded media until refreshed. Superseded artwork and DJ files are retained rather than deleted, and a generated file may remain unused if metadata saving fails. Scratch evidence is local and subject to cache pruning; no generated images or credentials were added to the repository.
