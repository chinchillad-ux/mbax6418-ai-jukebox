# Manual cover-art verification

## Run and actual inputs

- Executed: 2026-10-23 02:36:49–02:36:52 UTC.
- Branch: `feat/cover-art`.
- Track source: **representative Track**, not a recovered generated Track. This checkout contained no local `data/` audio or saved Track. Inputs match the instrumental example in `results/songs.md`.
- Track ID: `issue3-manual-instrumental`.
- Title: `Calm Ambient Electronic` (representative title following the existing song-generation naming convention; the historical title was not recorded in `results/songs.md`).
- Style: `ambient electronic`; mood: `calm`; duration: 10 seconds; instrumental (`is_vocal=False`); lyrics: `None`; audio path: `None`.
- Service: FLUX.2 klein 4B, base URL `http://dobolyi.com:9006/v1`, model `black-forest-labs/FLUX.2-klein-4B`.
- Configuration: no repository `.env` existed. The shared API key and service settings were read from the local class handout into this process's environment, then consumed by the existing `load_settings()`. No credentials were printed, hardcoded, or written into the repository.
- Exactly **one** call to the existing `generate_cover(track)`, with no retries. No song generation or port-9000 calls.
- Request: `POST /v1/images/generations`; `n=1`, `size=1024x1024`, `response_format=b64_json`.

Prompt:

> Create original square album artwork for "Calm Ambient Electronic". Musical style: ambient electronic. Mood: calm. Use expressive imagery, color, and composition to reflect this music. Do not copy an existing album cover; no lettering, logos, or watermarks.

## Expected result

One complete, decodable PNG under `data/covers/`; `cover_path` assigned to that file on the same Track without changing other fields. Artwork should evoke calm ambient electronic music. Generated media must remain Git-ignored.

## Verified observed result

- Generation succeeded on the first call without a generation error.
- Saved relative path: `data/covers/0b4407fd75a04b6aab3ef99d36a6c69a.png`.
- Saved absolute path: `C:\Users\combs\mbax6418-ai-jukebox\data\covers\0b4407fd75a04b6aab3ef99d36a6c69a.png`.
- PNG signature confirmed; Pillow `Image.verify()` passed; reopening and `Image.load()` successfully decoded the pixels.
- Image: PNG, 1024 × 1024 pixels, RGB; file size: 3,147,861 bytes.
- Returned object is the same Track. Its `cover_path` resolves to the saved file; all other Track fields remained unchanged.
- `git check-ignore -v` matched `.gitignore:21:data/` for this PNG. `git ls-files -- <image-path>` returned no entry: the image is ignored and untracked.

## Subsequent real-song integration evidence

The initial check below used representative metadata. The later sample-generation record in [samples.md](samples.md) documents covers generated for three actual class-service songs, the generation prompts, regenerated artwork after feedback about lettering, and final exact-title overlays. The sample integration tests validate the three cover files and their manifest associations. This is existing teammate evidence, not a new live generation or browser check performed during close-out.

The updated class handout specifies `http://dobolyi.com:9006/v1` as the cover base URL. The configuration example has been corrected accordingly; the client appends `/images/generations`.

## Visual assessment and limitations

Visual inspection was completed by sending the saved PNG to the class Qwen vision service on port 9001. This is a model-assisted assessment, not a human review or a claim that the primary assistant directly viewed the pixels.

- **Reported visible content:** square artwork with rounded corners; a still lake reflecting a twilight sky; dark mountains and pine-tree silhouettes; indigo sky, stars, and pastel pink/peach/yellow clouds. Dark rocky foreground includes a glowing cyan/magenta ribbon-like form. The vision model reported no visible text or logos.
- **Subjective fit:** the still water, soft light, and spacious landscape support the title's calm/ambient character. The glowing cyan/magenta accent suggests an electronic aesthetic. This is a reasonable visual match to the supplied title, style, and mood, not an objective measurement of musical correspondence.
- **Inspection errors:** the standard image-inspection tool and delegated fallback both failed with `401 Unauthorized`. The direct class vision request succeeded, but its first answer was truncated by the response-token limit; a second inspection of the same saved PNG with a larger limit returned a complete assessment. These were inspection requests, not additional FLUX cover generations. The FLUX generation count remains exactly one.

There was no locally available generated audio to listen to or compare against. This run verifies cover generation for representative documented metadata, not end-to-end association with a recovered Issue #2 audio file. Any assessment of the artwork's musical fit is subjective. This instrumental case does not manually verify lyric-conditioned imagery.
