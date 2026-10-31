# Creative song title generation

Implemented and tested on 2026-10-29 (Windows / Python 3.12).

The former mood + style naming formula is replaced by a class-Qwen
chat-completions request. Vocal titles are conditioned on up to 4000 characters
of the song's original lyrics, plus style/mood. Instrumental titles use
style/mood and request an imagined scene. The system prompt requests a short,
evocative original English title as JSON and explicitly rejects concatenating
the mood and genre. Context is supplied as JSON data in a separate user message.

The response must be a nonempty string of at most 80 characters/12 words,
without control characters; a bare mood/style concatenation is rejected.
Simple fenced JSON responses are supported. The title request runs only after
the generated song has passed audio validation. If the service fails or the
response is invalid, audio is preserved with an Untitled Track + short ID name.
The returned Track already has its chosen title before the app generates its
cover or saves the record. Existing songs and titles are not rewritten.

## Verification

- 19 targeted music/title tests passed.
- Full suite: **219 passed, 17 existing Gradio deprecation warnings**.
- Tests verify vocal/instrumental request context, class endpoint/model routing,
  JSON/fenced-JSON responses, rejected generic/empty/malformed/oversized titles,
  interrupted transfers, and validated audio retained on title-service failure.
- Two live-check attempts were made. The first title request failed with a safe
  service-unavailable error. A subsequent Qwen /models reachability request timed
  out before another title request was attempted. Therefore no successful live
  Qwen title or full new-song/browser run is claimed here. Naming behavior is
  verified with mocked responses; live service verification remains pending.
- No real song audio was generated for the live check and no credentials were
  printed or committed.

The tested music module was installed in the user's extracted app with a backup
of the old module kept in the review workspace. The cover-title fix, removal
control and studio theme were checked and preserved. Restart is required.

## Live-response diagnosis and correction

A later live reproduction revealed the naming failure: the original 128-token
request ended with finish_reason=length, content=null, and all 128 completion
tokens counted as reasoning tokens. The fallback was therefore being triggered
without any title text. This was an application request-budget/mode bug, not
evidence that the model chose an Untitled Track name.

The title request now sets chat_template_kwargs.enable_thinking=false, requests
JSON-object output, and allows 256 output tokens. A diagnostic request returned
a title with finish_reason=stop and zero reasoning tokens. The actual title
helper then succeeded twice: Backroad Dreaming for the user's existing fallback
song's lyrical context, and Neon Dawn Rising for a Hopeful/Electronic
instrumental. Existing saved records were not changed by these checks. No new
music, artwork, or DJ speech was generated. This successful live check supersedes
the earlier pending-service-verification note. Full browser new-song testing
after restarting still remains for the user.

The creation status now explicitly warns when Qwen naming failed and an Untitled
Track fallback was used, while confirming that the music is saved. Added
regressions cover reasoning-only output and the visible saved-audio warning.
Current results: **21 targeted tests passed; 221 tests passed, 17 existing
warnings in the full suite**. The corrected music module and status-message-only
patch were applied to the extracted app, preserving all its other installed
features. Restart is required.
