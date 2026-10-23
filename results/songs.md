# Song-generation verification

Manual endpoint checks ran on 2026-10-22. Credentials, endpoint payloads,
generated lyrics, and audio files are intentionally excluded from this report.
Generated audio remains under ignored `data/songs/`.

| Track | Inputs | Result |
| --- | --- | --- |
| Instrumental | ambient electronic; calm; 10 seconds; vocal: no | Generated successfully, passed decode/duration validation, and played locally. |
| Vocal | indie pop; hopeful; 10 seconds; vocal: yes; lyrics: auto-generated | Qwen produced original lyrics; ACE-Step generated audio successfully; it passed decode/duration validation and played locally. |

Duration validation accepts an observed duration within the larger of 3 seconds
or 25% of the requested duration. Unit tests mock all class endpoints; the
manual checks above exercise the real asynchronous submit, poll, and download flow.
