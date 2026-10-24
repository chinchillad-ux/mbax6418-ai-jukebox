# AI DJ verification (issue #4)

Manual service checks ran on 2026-10-24 (UTC-06:00). Credentials are not
printed, hardcoded, logged, or committed: the API key lives only in the
local gitignored `.env`, read by the existing `load_settings()`. The
reserved agent endpoint was never called. The class endpoint handout was
consulted for request formats only and remains outside the repository.

## Run and actual inputs

- Branch: `feat/ai-dj` (created from `main`; no `feat/ai-dj` branch existed
  at the start of this issue).
- Services (live, verified before coding):
  - Commentary: class Qwen service (chat-completions-style JSON request,
    temperature 0.7). Request shape confirmed against the published service
    API schema.
  - Speech: class Chatterbox speech service (text-to-speech; default voice,
    or an MP3/WAV voice reference passed as base64 `ref_audio`). Request
    shape confirmed against the published service API schema.
- Real generated Track (exactly one song generation): title
  `Calm Ambient Electronic`, style `ambient electronic`, mood `calm`,
  10 seconds, instrumental (`is_vocal=False`), saved under
  `data/songs/a3b8ec007dda4b2a993014353645eb9b.mp3`.

Commentary prompt sent to Qwen:

> Write 2 to 4 short, natural English sentences that an upbeat radio DJ
> would say aloud to introduce the next song between tracks. Do not write
> generic filler: be specific to this exact track, mention its title
> "Calm Ambient Electronic" naturally in the commentary, and describe its
> style (ambient electronic) and mood (calm). Do not mention instructions,
> prompts, AI, or songwriting, and do not quote the lyrics. Speak only the
> sentences a listener would hear. This track is instrumental, with no
> vocals or lyrics.

## Expected result

- `commentary_for_track(track)` returns 2-4 spoken sentences specific to the
  track and stores them on `track.dj_commentary`.
- `speak(text)` returns a saved MP3 path under `data/dj/` using the default
  voice; `speak(text, voice_ref_path=...)` uses the reference voice, keeping
  any reference copy only under `data/voice-refs/`.
- All generated media and references remain Git-ignored and untracked.

## Verified observed result

- Commentary (one real Qwen call): 2 sentences, 212 characters, stored on the
  track (`track.dj_commentary == returned text`):

  > We're taking a quick breather now, folks, so grab a seat and let go of the
  > stress with "Calm Ambient Electronic". These lush ambient electronic
  > soundscapes are here to reset your vibe and keep things super chill.

  Grounding: mentions the exact title, names the style ("ambient electronic
  soundscapes"), and echoes the calm mood ("let go of the stress", "reset your
  vibe", "chill"). Not generic filler.
- Default-voice speech (one real Chatterbox call): saved to
  `data/dj/c3f6ed50cf7f4b749006fff7451743e4.mp3`; 159,404 bytes; ffprobe
  reports `mp3`, duration 9.88 s.
- Custom-voice speech (one real Chatterbox call with a reference): the
  default-voice MP3 above was used as the MP3 voice reference (self-generated
  audio — no third-party or human recording). The reference was copied to
  `data/voice-refs/ab0111e4a9764839b9b0efee8f7c8ec6.mp3`, the request carried
  a base64 `data:audio/mpeg;...` `ref_audio`, and the clone was saved to
  `data/dj/1c9ed57f91ba43178da58dd877fe5e2d.mp3`; 47,276 bytes; ffprobe
  reports `mp3`, duration 2.88 s (spoken text: "Thanks for listening. That
  was the custom voice check.").
- After the run, the copied reference was deleted; `data/voice-refs/` is
  empty and nothing voice-related is committed.
- `git check-ignore -v` matched the `.gitignore` `data/` rule for the two DJ
  audio files and the generated song; `git ls-files` reports none of them as
  tracked.
- Full automated suite: **97 passed** (45 new `tests/test_dj.py` cases:
  commentary grounded in track metadata, commentary saved on the correct
  Track, default-voice payload and saved file, custom MP3/WAV references,
  reference placement under `data/voice-refs/`, malformed service responses,
  readable failures, cleanup of incomplete files).

## Limitations

- Commentary quality is assessed by reading the generated text; there is no
  objective measure of "DJ-likeness". Sentence count was requested as 2-4 but
  is not programmatically enforced (the model returned 2).
- Audio correctness was verified by ffprobe decode/duration and file size,
  not by human listening.
- The voice clone was verified end-to-end with a service-generated reference,
  not a human voice recording; a human recording (MP3/WAV, 1-60 s per the
  service) is expected to work through the same `ref_audio` path.
- Only an instrumental track was exercised manually. The vocal/lyrics path
  (lyrical-theme conditioning of the prompt) is covered by mocked unit tests
  but not by this live run.
- One 10-second song was generated in this run. No cover art or queue
  integration was exercised (issue #5 owns playback integration).
