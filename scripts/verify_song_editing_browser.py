"""Optional real-Chrome regression check; synthetic transport, isolated library.

Run: uv run --with playwright python scripts/verify_song_editing_browser.py \
    --evidence /absolute/scratch/path --chrome /path/to/chrome
No live AI requests or user's browser profile are used.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import wave
from io import BytesIO
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--chrome", required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", choices=["all", "rename", "switch"], default="all")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    args.evidence = args.evidence.resolve()
    args.evidence.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="library-", dir=args.evidence))
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    os.environ["GRADIO_TEMP_DIR"] = str(root / "gradio-cache")
    os.chdir(root)

    from PIL import Image
    from playwright.sync_api import expect, sync_playwright

    from jukebox import app, cover
    from jukebox.config import Settings
    from jukebox.library import Library
    from jukebox.models import Track

    originals = {}
    for name, color in [("a", "blue"), ("b", "green"), ("c", None), ("d", None)]:
        audio = root / f"{name}.wav"
        with wave.open(str(audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\x00\x00" * 8000)
        image = root / f"{name}.png"
        if color:
            Image.new("RGB", (80, 80), color).save(image)
        track = Track(name, f"Song {name.upper()}", "pop", "happy", 1, True,
                      lyrics="Unchanged lyrics", audio_path=str(audio),
                      cover_path=str(image) if color else None,
                      dj_audio_path=str(audio), dj_commentary="Old introduction")
        Library().add(track)
        originals[name] = track.to_dict()
    original_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in root.glob("*.*")}
    started, release = threading.Event(), threading.Event()
    release.set()
    requests = []
    completed = []
    cover.load_settings = lambda: Settings(
        "dummy-key", "http://example.test:9001/v1", "http://example.test:9006/v1",
        "http://example.test:9007", "http://example.test:9008", "qwen", "flux", "ace", "speech")

    def transport(req, **kwargs):
        prompt = json.loads(req.data)["prompt"]
        requests.append(prompt)
        started.set()
        if not release.wait(25):
            raise TimeoutError("Browser test did not release synthetic transport")
        if "outage" in prompt:
            completed.append(prompt)
            raise OSError("Synthetic outage")
        image = BytesIO()
        Image.new("RGB", (80, 80), "red").save(image, "PNG")
        completed.append(prompt)
        return BytesIO(json.dumps({"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]}).encode())

    cover.urlopen = transport
    report = {"browser": "isolated headless Chrome", "live_ai_calls": 0, "cases": [], "passed": False}
    demo = app.build_app()
    try:
        _, url, _ = demo.launch(server_name="127.0.0.1", prevent_thread_lock=True,
                                quiet=True, allowed_paths=[str(root)])
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
            page = browser.new_page(viewport={"width": 1280, "height": 1100})
            page.goto(url)
            page.get_by_role("tab", name="My Library").click()
            page.wait_for_timeout(700)
            picker = page.get_by_label("Choose Any Saved Song", exact=True)
            title = page.get_by_label("Song title", exact=True)
            description = page.locator("textarea").nth(1)
            regenerate = page.get_by_role("button", name="Regenerate Album Cover", exact=True)
            retry = page.get_by_role("button", name="Retry Missing Album Cover", exact=False)

            def choose(name, pending=False):
                picker.click()
                page.get_by_role("option", name=name + (" (cover pending)" if pending else ""), exact=True).click()
                expect(title).to_have_value(name)
                page.wait_for_timeout(300)

            def image_matches(name):
                images = page.locator("img").evaluate_all(
                    "els => els.map(e => ({alt:e.alt, src:e.src})).filter(e=>e.src.startsWith('http://127.0.0.1'))")
                gallery = next(x["src"] for x in images if x["alt"] == name)
                editor = next(x["src"] for x in images if x["alt"] == "")
                assert editor == gallery, (name, images)
                return images

            def record(name):
                page.screenshot(path=str(args.evidence / f"{name}.png"), full_page=True)
                report["cases"].append(name)

            def block():
                started.clear()
                release.clear()

            def wait_started():
                assert started.wait(10), "Synthetic transport was not called"

            def wait_done(count):
                deadline = time.monotonic() + 15
                while len(completed) < count and time.monotonic() < deadline:
                    page.wait_for_timeout(100)
                assert len(completed) == count
                page.wait_for_timeout(1200)  # allow chained browser events to settle

            choose("Song B")
            if args.case in ("all", "rename"):
                title.fill("Renamed B")
                page.get_by_role("button", name="Save Song Title", exact=True).click()
                expect(page.get_by_text("🎵 Now selected: Renamed B", exact=True)).to_be_visible()
                expect(picker).to_have_value("Renamed B")
                assert Library().get("b").title == "Renamed B"
                assert Library().get("b").dj_audio_path is None
                record("rename-label")
            b_title = "Renamed B" if args.case != "switch" else "Song B"
            if args.case in ("all", "switch"):
                block()
                description.fill("slow red artwork")
                regenerate.click()
                wait_started()
                choose("Song A")
                description.fill("Unsubmitted A draft")
                release.set()
                wait_done(1)
                expect(title).to_have_value("Song A")
                expect(description).to_have_value("Unsubmitted A draft")
                image_matches("Song A")
                assert Library().get("a").cover_path == originals["a"]["cover_path"]
                assert Library().get("b").cover_description == "slow red artwork"
                assert "New album cover saved" not in page.locator("body").inner_text()
                record("slow-cover-switch")
            if args.case == "all":
                choose(b_title)
                image_matches(b_title)
                old_cover = Library().get("b").cover_path
                block()
                description.fill("outage description to keep")
                regenerate.click()
                wait_started()
                description.fill("Edited while failing; keep this draft")
                release.set()
                wait_done(2)
                expect(description).to_have_value("Edited while failing; keep this draft")
                expect(page.get_by_text("⚠️ Could not regenerate or save artwork. Previous cover kept; please retry.", exact=True)).to_be_visible()
                assert Library().get("b").cover_path == old_cover
                image_matches(b_title)
                record("failure-preserves-draft")
                # Retry a missing cover, then select another song during transport.
                choose("Song C", pending=True)
                block()
                retry.click()
                wait_started()
                choose("Song A")
                release.set()
                wait_done(3)
                image_matches("Song A")
                expect(page.get_by_text("🎵 Now selected: Song A", exact=True)).to_be_visible()
                assert Library().get("c").cover_path
                record("missing-cover-switch")
                choose("Song C")
                image_matches("Song C")
                record("completed-retry-reselection")
                # Queue the other cover action while generation is blocked.
                choose(b_title)
                block()
                description.fill("queued red B")
                regenerate.click()
                wait_started()
                choose("Song D", pending=True)
                retry.click()
                page.wait_for_timeout(300)
                choose("Song A")
                release.set()
                wait_done(5)
                image_matches("Song A")
                expect(title).to_have_value("Song A")
                assert Library().get("d").cover_path
                assert Library().get("b").cover_description == "queued red B"
                record("queued-regenerate-and-retry")
                # Return to the original ID while its request is in flight.
                choose(b_title)
                block()
                description.fill("return to B")
                regenerate.click()
                wait_started()
                choose("Song A")
                choose(b_title)
                description.fill("Next B draft")
                release.set()
                wait_done(6)
                image_matches(b_title)
                expect(description).to_have_value("Next B draft")
                assert Library().get("b").cover_description == "return to B"
                record("switch-away-and-back")
                block()
                description.fill("outage while switching")
                regenerate.click()
                wait_started()
                choose("Song A")
                description.fill("A draft survives B outage")
                release.set()
                wait_done(7)
                expect(description).to_have_value("A draft survives B outage")
                image_matches("Song A")
                assert "Could not regenerate" not in page.locator("body").inner_text()
                record("failure-after-selection-switch")
                page.reload()
                page.get_by_role("tab", name="My Library").click()
                page.wait_for_timeout(700)
                choose(b_title)
                expect(description).to_have_value("return to B")
                image_matches(b_title)
                record("reload-persistence")
            for track in Library().list():
                original = originals[track.id]
                assert track.audio_path == original["audio_path"]
                assert track.lyrics == original["lyrics"]
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
                       for p, digest in original_hashes.items())
            report.update(passed=True, requests=len(requests), completed=len(completed),
                          immutable_fixture_files=len(original_hashes), images=image_matches(b_title if args.case != "switch" else "Song A"))
            browser.close()
    finally:
        release.set()
        demo.close()
        (args.evidence / "browser-results.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
