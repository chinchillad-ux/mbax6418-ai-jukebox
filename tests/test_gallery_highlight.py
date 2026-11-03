"""Gallery highlight: dropdown selection highlights the matching album tile."""

import gradio as gr
import pytest

from jukebox.app import library_cover_selection
from jukebox.library import Library
from jukebox.models import Track


def _seed(tmp_path):
    import os
    os.chdir(tmp_path)
    lib = Library()
    lib.add(Track(id="a", title="Alpha", style="Pop", mood="Happy",
                  duration_seconds=30, is_vocal=True, cover_path="data/covers/a.png"))
    lib.add(Track(id="b", title="Beta", style="Rock", mood="Energetic",
                  duration_seconds=30, is_vocal=False, cover_path="data/covers/b.png"))
    lib.add(Track(id="c", title="Gamma", style="Jazz", mood="Calm",
                  duration_seconds=30, is_vocal=False))  # no cover, not in gallery


def test_highlight_first_cover(tmp_path):
    _seed(tmp_path)
    result = library_cover_selection("a")
    assert isinstance(result, dict)
    assert result.get("selected_index") == 0


def test_highlight_second_cover(tmp_path):
    _seed(tmp_path)
    result = library_cover_selection("b")
    assert result.get("selected_index") == 1


def test_coverless_track_clears_highlight(tmp_path):
    _seed(tmp_path)
    result = library_cover_selection("c")
    # Must explicitly clear the previous selection, not merely skip it.
    assert "selected_index" in result
    assert result["selected_index"] is None


def test_unknown_track_skips(tmp_path):
    _seed(tmp_path)
    result = library_cover_selection("missing")
    assert result is None or result.get("__type__") == "update"
    assert "selected_index" not in result
