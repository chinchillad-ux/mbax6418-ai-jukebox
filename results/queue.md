# Issue #5 draft: library and playback logic

Owner: BAAndrewsDev. Tested on 2026-10-23 against main commit
`d21365f6ef383543eac06b8dcedd935bb32cd62f` plus this draft's changes.

## Completed automated checks

Command from the repository root, after `uv sync --extra dev`:

```text
python -m pytest tests -q
```

The review environment used the project's virtual-environment Python and a
workspace-local pytest temporary directory on Windows / Python 3.12.
Result: **56 passed**. All playback tests use an injected clock and fake audio
transport. No class services were called by these tests.

| Inputs / scenario | Expected behavior | Actual result |
| --- | --- | --- |
| Add two tracks, then update the first ID | Two tracks, updated metadata, stable insertion order after reload | Passed |
| Generated and sample asset paths, Unicode lyrics | Every Track field survives a library restart | Passed |
| Mutate a returned Track | Saved/queued objects remain unchanged | Passed |
| Invalid JSON, schema version, duplicate IDs | Report a readable error without replacing the file | Passed |
| Simulated failure during atomic file replacement | Previous file and in-memory library survive; temporary file removed | Passed |
| Two tracks with speech durations 2/3 seconds and songs 10/8 seconds | speech 1, song 1, speech 2, song 2, stopped | Passed |
| Backend refuses overlapping play calls | Stop precedes every subsequent clip | Passed |
| Pause speech or song for 100 simulated seconds | Position frozen; resume retains elapsed playback time | Passed |
| Skip during speech or song | Skip the entire track and start the next introduction | Passed |
| Skip while paused | Select next track, remain paused, start no audio until resumed | Passed |
| Tick arrives 100 seconds late | Start the next clip at position zero, without truncation or overlap | Passed |
| Missing audio, invalid/zero/nonfinite duration | Reject the whole enqueue batch without changing existing queue | Passed |
| Backend start fails | Safe error status, current track retained, retry succeeds | Passed |
| Backend stop fails | Enter error state; do not start another clip until stop succeeds | Passed |

## Interface for issue #6

`Library(path="data/library.json")` loads saved metadata at construction.
`add(track)` inserts or updates by ID and saves immediately. `list()` returns
tracks in insertion order; `get(id)` returns a Track or None. Returned objects
are copies; call `add(updated_track)` to save generated audio/cover/DJ paths.
The versioned JSON contains full `Track.to_dict()` records. It stores metadata,
not audio. Generated files, uploads, and voice references must remain in `data/`.

`Player(backend, clock=time.monotonic)` accepts an object implementing the
`AudioBackend` protocol in `jukebox/player.py`:

- `duration(path)` inspects the actual clip and returns seconds.
- `play(path)` starts that clip from the beginning and returns after startup,
  without waiting for playback to finish.
- `pause()` / `resume()` retain the actual clip position.
- `stop()` silences and resets the clip before returning.

Enqueue with `enqueue([track, ...])`; call `play()`, `pause()`, `skip()`, or
`stop()` from controls. `play()` also retries the current clip from its beginning
after an error. `stop()` discards the current track but keeps future queued
tracks. `skip()` while stopped drops the first queued track without starting it.
Call `tick()` regularly to advance automatically. `status()` is a snapshot and
does not perform transitions. Both return `PlaybackStatus`: state, current Track,
speech/song phase, clip position/duration, upcoming Tracks, and safe error text.
An incomplete track stays in the library but cannot be enqueued until it has
both music and DJ audio with valid durations.

All controller calls must run serially on one UI/controller thread. A browser
audio adapter must use media position/ended events to synchronize its clock;
server wall time alone is insufficient when the browser is buffering. It must
also implement the actual pause/resume/stop operations. The draft does not yet
include that UI adapter, physical audio-output testing, or browser autoplay
handling; those need integration with issue #6. Do not treat mocked sequencing
tests as evidence that the finished browser plays sound correctly.

## Design judgment and investigated failure

The queue uses actual audio durations rather than requested song duration, and
explicitly stops each clip before starting another. The tests use 10-second
audio for a Track requesting 30 seconds to verify that distinction. A late poll
starts the next clip at zero instead of carrying over elapsed wall time. This
preserves the entire next introduction/song, at the cost of a possible gap if
the UI polls infrequently. The final UI should use audio events and frequent
updates, then verify the result with real playback.

The simulated disk-replacement failure verifies an important persistence limit:
a save must succeed before the in-memory library changes. Writing a temporary
file beside the destination and replacing atomically preserves the previous
library on failure. This is a single-controller library, not a concurrent
multi-process database; simultaneous writers are unsupported.

## Pending before issue #5 can be completed

- Merge cover art (#3 / PR #11) and DJ commentary/speech (#4), then rebase this
  draft and verify their actual function contracts.
- Review the teammate's DJ PR as BAAndrewsDev. No DJ PR existed when this draft
  was prepared, so no approval or completed teammate review is claimed.
- Use those merged functions and the real class endpoints to generate three
  original sample songs and covers, including at least one vocal with
  AI-generated lyrics and one instrumental. No samples were generated here.
- Commit only the required first-party sample assets and `samples.json` under
  `assets/samples/`. Keep all session media and reference uploads in `data/`.
- Record exact sample prompts, parameters, steps, and actual outcomes in
  `results/samples.md`; do not invent passing manual results.
- Integrate the samples/library/queue, test real playback in the UI, rerun the
  full suite, and request Delcers' review when the PR is ready.

This draft does **not** close issue #5 or claim its sample/integration checks.
