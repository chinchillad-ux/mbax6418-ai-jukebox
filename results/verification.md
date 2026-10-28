
# Gradio Interface – Playback Verification (Issue #6)

Date: October 26, 2026
Branch: feat/gradio-interface

## Manual Browser Testing

Verified that starting playback in one audio player
pauses the previously playing audio without removing
the loaded audio file.

All six player combinations passed in both directions:

- Generated Song ↔ DJ Playlist: PASS
- DJ Introduction ↔ DJ Playlist: PASS
- Generated Song ↔ Library Song: PASS
- Library Song ↔ DJ Introduction: PASS
- Generated Song ↔ DJ Introduction: PASS
- Library Song ↔ DJ Playlist: PASS

Result: No overlapping audio during these tests.
Audio files remained loaded and playable after switching.


## DJ Playlist Skip Tests

- Skip while paused: PASS
  Paused the current DJ playlist track, then clicked
  Skip to Next Song. The playlist advanced as expected.

- Skip near clip completion: PASS
  Clicked Skip to Next Song near the end of the
  currently playing clip. The playlist advanced
  as expected.


## Automated Testing

Command:
uv run --extra dev pytest -q

Result: 163 passed, 2 warnings.

The warnings did not cause test failures.
Both warnings are Gradio deprecation notices for the `theme` and `css` parameters in `gr.Blocks()`. These parameters will need to move to `.launch()` when upgrading to Gradio 6.0. Neither warning affects the current functionality or test results. No changes are required for this PR.

## Bundled DJ speech playback capture (Issue #7, PR #17)

Captured October 27, 2026, at 18:16 MDT in automated headless Chrome 156.0.8078.49 on macOS. This supplements, rather than replaces, the October 26 results above.

- **Source:** PR #17 head `ce727e8b0100e1aff71bc6d6fd94822c71527804`, exported with `git archive`; all 55 tracked files matched their Git blobs byte-for-byte. Application code, dependencies and bundled assets were unchanged from documented merge `47bf55a8ec10498b3a4534e86d9461a68ae271b1`.
- **Isolation:** unchanged app, separate temporary library/cache and Chrome profile, fresh loopback server, 1440-pixel light-theme viewport. Credential variables were removed, dotenv and analytics disabled, and nonlocal Python connections/browser requests blocked. No AI generation button was clicked, no live AI call was made, and no synthetic audio or replacement service response was used.
- **Actions:** clicked **Load 3 Demo Songs**, confirmed three persisted tracks, opened **AI DJ**, refreshed songs, selected Copper Sunrise, and queued Copper Sunrise → Rain on Glass → Neon Night Drive. Clicked the actual **Start DJ Set** button. The status became **Now introducing: Copper Sunrise**, and its waveform player began playback without a second play click in this session.
- **Expected:** the first queue item plays its bundled DJ introduction while the queue remains visible.
- **Observed:** the waveform player's HTML audio element had `paused=false`, `ended=false`, `readyState=4`, and duration `14.08` seconds. `currentTime` advanced from `0.164335` to `1.969957` seconds across an approximately 1.8-second wait. Immediately before/after the screenshot it advanced from `2.329521` to `2.430896` seconds, still unpaused and within the introduction.
- **Source identity:** the active `currentSrc` was a local browser blob. Fetching that blob and hashing its bytes matched `assets/samples/copper-sunrise-dj.mp3` exactly: SHA-256 `9707c979248e47e0ae61cce2471700d088a8575fc13a83f145fe96febc58a417`. This establishes that the playing source was the selected track's real bundled speech, not its music or synthetic media.
- **Artifact:** [active DJ playlist screenshot](../screenshots/dj-playlist.png), 1440 × 1768 pixels, SHA-256 `8fbc7aa80b7efb1d2a4037208af299fa708341f7c28f2ea844a2a3fb6e64fae8`. The unaltered full-page capture visibly shows the three-track queue, introduction status, elapsed time near 0:02, waveform progress, and pause control. Visual inspection found no clipped controls or exposed credentials; the horizontal-overflow check passed.
- **Cleanup:** zero browser page errors and zero nonlocal Python connection attempts in the successful run. The owned browser and app were closed; a connection check confirmed the capture port was closed.
- **Harness correction:** two initial attempts targeted the hidden fallback audio element rather than the active waveform audio element; they failed observation/selector checks and closed their browser/server. The successful capture inspected the waveform audio and verified its blob bytes. No application change was needed.

**Limits and remaining review gate:** Chrome was launched with audio output muted. Advancing HTML audio time and a matching source demonstrate browser playback, not human audible listening, speech quality, full queue progression, pause/resume, skip, or cross-browser autoplay. The independent teammate installation from a **GitHub-downloaded ZIP**, including the required song generation, cover generation, and DJ-feature exercise and any fixes, is **still pending**. This capture does not complete that test, close issue #7, or constitute approval or merge authorization.
