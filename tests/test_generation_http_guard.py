"""HTTP regression: rapid duplicate generation requests must never strand
the generation lock.

The guard is owned by each request (non-blocking lock acquired in the handler,
released in finally). There is no shared state a duplicate could corrupt, so
after any burst of rapid requests the next generation always succeeds.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from gradio_client import Client

from jukebox import app, music
from jukebox.models import Track


@pytest.fixture
def running_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    audio_file = tmp_path / "http-qa.mp3"
    audio_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 4096)

    def slow_generate(**kwargs):
        time.sleep(0.6)  # bounded delay so concurrent requests overlap
        return Track("http-qa", "HTTP Q&A Song", "pop", "happy", 30, False,
                     audio_path=str(audio_file))

    monkeypatch.setattr(app, "generate_song", slow_generate)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)
    monkeypatch.setattr(music, "_validate_audio", lambda path, requested_seconds: None)

    demo = app.build_app()
    _, url, _ = demo.launch(server_name="127.0.0.1", prevent_thread_lock=True,
                            quiet=True, allowed_paths=[str(tmp_path)])
    yield url
    demo.close()


def test_rapid_duplicate_requests_do_not_strand_the_lock(running_app):
    url = running_app
    client = Client(url, verbose=False)

    def generate():
        return client.predict("Pop", "Happy", 30, "Instrumental",
                              api_name="/create_song")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(generate) for _ in range(4)]
        results = [f.result(timeout=60) for f in futures]

    # Every request must either succeed or be rejected as already in progress;
    # none may deadlock, error, or leave the app wedged.
    for result in results:
        message = result[2].lower()
        assert result[0] is None or "already" in message or message.startswith("✅"), \
            f"unexpected result: {message}"

    # Recovery is the critical property: the lock released in finally, so the
    # next generation after the burst must succeed.
    final = client.predict("Pop", "Happy", 30, "Instrumental",
                           api_name="/create_song")
    assert final[2].startswith("✅"), f"lock was stranded: {final[2]}"
