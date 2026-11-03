# Final documentation verification — November 2, 2026

Brandon confirmed personal listening to the songs and DJ playback and confirmed that the team reviewed the README against the finished app. Technical checks below were performed with Codex assistance. The report separates confirmed human/team review from measured technical results; it does not claim an independent human voice-likeness assessment.

## Findings and corrections

- Windows installation succeeded with Python 3.11.16, uv 0.12.5, Gradio 5.50.0 and FFmpeg/ffprobe 9.0. OneDrive rejected uv hardlinks; `uv sync --frozen --extra dev --link-mode copy` resolved it. Installation took several minutes. README now documents this setup correction.
- The README's 204-test count and unverified-Windows statement were historical. The final extracted copy passed **263 tests, 42 warnings in 66.20 seconds**. One warning was a server-port collision while the app was also running. Repeating the manifest test on a separate port passed: **1 passed, 2 dependency deprecation warnings in 12.07 seconds**. The automated suite uses mocked service transport.
- The AI DJ picker initially kept server-startup choices, leaving later songs absent until manual refresh. PR #23 added page-load/tab-entry refresh while preserving valid selections. The final extracted app listed imported demos without manual refresh.
- PR #24's earlier duplicate guards were reviewed using mocked HTTP requests. The final revision uses a lock owned by each request on the nonqueued browser route. Concurrent requests rejected the duplicate, completed the original, and permitted a subsequent generation. Coverless-song selection explicitly clears the previous gallery selection.

## Earlier live feature checks (before the final ZIP)

| Input/action | Measured result |
|---|---|
| Pop / Happy / 30 seconds / Instrumental | Sunlight Dancing on Pavement: 30.000-second audio, no lyrics, 1024×1024 cover, saved library entry. Full audio decode passed. |
| Pop / Happy / 45 seconds / Vocals | Riding Rainbow Waves: 45.000-second audio, 409 characters of saved AI lyrics, distinct 1024×1024 cover, saved library entry. Full audio decode passed. |
| Default DJ for Riding Rainbow Waves | Song-specific commentary and 11.44-second decoded speech. |
| MP3-reference DJ for Sunlight Dancing on Pavement | Uploaded bundled class-generated Copper Sunrise DJ MP3; generated 17.16-second decoded speech. |
| WAV-reference DJ for the same instrumental | Uploaded a mono 24 kHz WAV converted from that bundled reference; generated 16.00-second decoded speech. Reference remained in ignored runtime storage. |
| Missing song selection | Readable selection error; selecting a song and retrying succeeded. Automated tests separately cover service failure and artwork retry. |
| Two new songs in a DJ set | Automatic introduction → music → next introduction → next music → completion. Pause/resume and skip worked. Inspected browser states showed one active audio element while playing and all paused after pause. |
| Refresh and page reload | Both new tracks remained saved and playable. |

Both new covers were visually inspected: cheerful colors and musical imagery suited to Happy/Pop, with readable correct titles. Human listening was later confirmed by Brandon; acoustic measurements of continuous non-overlap and voice similarity were not performed.

## Final extracted-ZIP checks

The user's GitHub-downloaded `mbax6418-ai-jukebox-main (3).zip` identifies commit `9dc926dccda13d4f75eedd9d8dda18fa37e252a5`, matching GitHub main when checked. Its entries included six sample MP3s, three covers, source, dependency information, configuration examples and documentation, with no `.env`, runtime `data/`, or `.venv/` entries.

The extracted A3 Final copy was installed into its own environment. Application source matched the reviewed revision apart from line endings. The previous server was stopped; this copy launched at the local Gradio address. It began with an empty library, displayed the new empty-library guidance, imported all three demos, and populated AI DJ automatically. A new default-voice introduction for Rain on Glass generated successfully and loaded as approximately 18 seconds in the browser. No application source fixes were made during this final launch check.

These final-ZIP checks do not repeat every earlier live generation and playback case. The historical teammate macOS installation and sample-generation provenance remain documented separately in `verification.md` and `samples.md`.

## Submission follow-through

This documentation update requires a new merged commit and matching GitHub-downloaded ZIP if included in the submission. Do not submit the previously prepared commit ID/PDF with a different ZIP. Keep all local `.env`, environments, generated runtime media, uploads and voice references outside the submission. Confirm contributor/reviewer participation, original prompt process history, and instructor access through grading separately; these technical checks do not establish them.
