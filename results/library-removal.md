# Library removal verification

Tested on Windows / Python 3.12 on 2026-10-29.

The library now supports remove(track_id) with the same process write lock,
reload-before-write and atomic replacement as add/update. Missing IDs are no-ops.
The shared atomic-save helper updates memory only after a successful save. No
media files are deleted. The UI exposes Remove from Library by stable song ID.
A successful removal clears this browser's four audio outputs and DJ state,
refreshes the library count/gallery/dropdowns, retains valid remaining playlist
selections, and clears the removed song's editor. Failures do not clear playback.

## Actual automated results

- 27 targeted library/removal tests passed.
- Full suite: **216 passed, 22 warnings**. Warnings are existing Gradio API
  deprecations, emitted by additional app-build/HTTP test invocations.
- Verified persistence after removal and restart, removal of the final record,
  no-op missing IDs, retained audio/cover/DJ files, protection against stale
  Library instances overwriting newer records, and atomic-save failure recovery.
- A slow cover/DJ metadata update cannot restore a removed record: update raises
  LibraryError because the latest record no longer exists.
- Verified UI reset output values, remaining playlist selections, missing-ID
  handling, save failure handling, and restored bundled samples through the
  existing Load 3 Demo Songs function.
- A real local Gradio HTTP request to /remove_library_song successfully removed
  one fixture record, retained the other, and retained the removed track's media.
- No real AI service requests, actual user-song removals, physical playback or
  browser click/listening verification were performed by these tests.

Other open browsers may retain cached media until refresh. The app remains a
single-process local library; this change does not implement cross-process or
cross-browser media coordination. User files remain on disk deliberately.
