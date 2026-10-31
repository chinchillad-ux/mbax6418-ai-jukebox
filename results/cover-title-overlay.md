# Exact titles on newly generated covers

## Problem and resulting behavior

On 2026-10-29, the user generated a vocal Electronic / Energetic / 120-second
song in the extracted GitHub ZIP. The default FLUX prompt included literal
title and lyrics, and the artwork contained misspelled title/lyric lettering.
The bundled samples had already been corrected separately.

All generate_cover callers now request art without literal titles or lyrics.
Style/mood and optional user visual direction remain in the prompt. The PNG is
validated as before, then Pillow draws the exact Track title over a dark lower
gradient before the temporary file is atomically published. Long titles wrap
and shrink to fit without ellipses. DejaVu Sans Bold is preferred when available;
Pillow's bundled scalable font is the fallback. Pillow >=10.1 is declared for
the scalable fallback API. Track metadata and existing media paths change only
after successful output creation. No additional service or paid API is used.

The generated title is part of the cover PNG, not a browser-only label. Renaming
an existing song does not rewrite its existing cover; regenerate its artwork to
update that title. Existing covers remain unchanged until regenerated.

## Automated validation

- Full suite: **211 passed, 17 existing warnings** on Windows / Python 3.12.
- After final text-free prompt strengthening: **39 cover tests passed**.
- Tests cover unchanged upper artwork, visible title pixels, long names up to
  200 characters, an unbroken 200-character name, accented Latin text, font
  fallback, and preserving the previous cover if rendering fails.
- Existing song-editor and local Gradio HTTP regression tests pass. Mocked
  generated-image fixtures now match the requested 1024x1024 size.
- No live AI requests are used in the automated tests.

## Live class-service check

Two real class FLUX requests used a representative Track titled
Energetic Electronic, style Electronic, mood Energetic, requested duration 120,
and synthetic lyric text that was deliberately excluded from both prompts.
No music or DJ speech was generated for this check.

The first output had a correctly typeset title but some small invented sign
lettering in the background. The prompt was strengthened to discourage signs,
storefronts, billboards, screens, and other objects that tend to contain text.
The second output is a valid 1024x1024 PNG, visually inspected with no unwanted
lettering visible and the exact title rendered on two readable lines. This is
one successful final-prompt example, not a guarantee that FLUX will never draw
letter-like marks. Preview is retained in the review workspace; runtime images
and credentials are not committed.

The tested cover module was copied to the user's extracted app after preserving
its previous module in the review workspace. The extracted app uses Pillow
11.3.0. It needs a restart to load the new code. The user's existing music,
library and credentials were not changed by this copy. End-to-end testing of a
new song through that restarted browser remains for the user to perform.
