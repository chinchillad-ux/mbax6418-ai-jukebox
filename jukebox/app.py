
import gradio as gr

import json
from jukebox.models import Track

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import (
    Request, build_opener, HTTPRedirectHandler, ProxyHandler
)
from urllib.error import URLError
from uuid import uuid4


from jukebox.music import generate_song, SongGenerationError

from jukebox.cover import generate_cover, CoverGenerationError

from jukebox.library import Library, LibraryError

from jukebox.dj import commentary_for_track, speak, DJError


def create_song(style, mood, duration, vocal_mode):
    """Generate a song and matching album cover."""
    try:
        track = generate_song(
            style=style.lower(),
            mood=mood.lower(),
            duration_seconds=int(duration),
            is_vocal=(vocal_mode == "Vocals")
        )

    except SongGenerationError as error:
        return None, None, f"⚠️ {error} Please try again."

    except Exception:
        return None, None, (
            "⚠️ Song generation failed. Please try again."
        )

    
    cover_warning = None

    try:
        track = generate_cover(track)

    except CoverGenerationError as error:
        track.cover_path = None
        cover_warning = (
            f"⚠️ Your song was saved, but the cover failed: {error}"
        )

    except Exception:
        track.cover_path = None
        cover_warning = (
            "⚠️ Your song was saved, but cover art failed."
        )

    try:
        Library().add(track)

    except LibraryError as error:
        return (
            track.audio_path,
            track.cover_path,
            f"⚠️ Song created, but saving failed: {error}"
        )

    if cover_warning:
        return (
            track.audio_path,
            None,
            cover_warning
        )

    return (
        track.audio_path,
        track.cover_path,
        f"✅ '{track.title}' and its cover were saved to your library!" + (
            "\n⚠️ Qwen could not generate a title. Your music is saved; rename it in My Library."
            if track.title.startswith("Untitled Track ") else ""
        )
    )


    


def rename_song(track_id, title):
    """Rename metadata only; old spoken titles must not remain playable."""
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        return "⚠️ Enter a song title (1–200 characters)."
    try:
        library = Library()
        track = library.get(track_id) if track_id else None
        if track is None:
            return "⚠️ Please select a saved song."
        title = title.strip()
        if title == track.title:
            return "No change: this song already has that title."
        library.update(track_id, title=title)
        return "✅ Title saved. Generate a new DJ introduction for the renamed song."
    except LibraryError as error:
        return f"⚠️ Could not rename song: {error}"


def regenerate_cover(track_id, description):
    """Generate replacement art; keep the saved cover until everything succeeds."""
    old_cover = None
    try:
        library = Library()
        track = library.get(track_id) if track_id else None
        if track is None:
            return None, "⚠️ Please select a saved song."
        old_cover = track.cover_path
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 2000:
            return old_cover, "⚠️ Enter a cover description (1–2000 characters)."
        generated = generate_cover(track, description=description.strip())
        if not generated.cover_path:
            return old_cover, "⚠️ Cover generation returned no artwork. Previous cover kept."
        library.update(track_id, cover_path=generated.cover_path,
                       cover_description=generated.cover_description)
        return generated.cover_path, "✅ New album cover saved. Your song audio is unchanged."
    except (CoverGenerationError, LibraryError):
        return old_cover, "⚠️ Could not regenerate or save artwork. Previous cover kept; please retry."
    except Exception:  # noqa: BLE001 - UI boundary must not expose service details.
        return old_cover, "⚠️ Could not generate album cover. Previous cover kept; please retry."


def refresh_after_cover(track_id, message):
    """Do not reload the editor after failure: keep the description for retry."""
    if not message.startswith("✅"):
        return gr.skip()
    return refresh_saved_song_choices(track_id)


def regenerate_editor_cover(track_id, description):
    """Keep slow results off visible components until selection is rechecked."""
    return track_id, *regenerate_cover(track_id, description)


def retry_editor_cover(track_id):
    return track_id, *retry_cover(track_id)


def show_cover_result(result, selected_id):
    """Apply to the current selection, never reload editable title/description.

    This runs as a separate event after generation, so selected_id is read
    from the browser after the slow request, not captured when it started.
    Read the latest persisted image rather than an older queued result.
    """
    if not result:
        return gr.skip(), gr.skip(), gr.skip()
    track_id, _, message = result
    choices = refresh_after_cover(selected_id, message)
    if track_id != selected_id:
        return gr.skip(), gr.skip(), choices
    if not message.startswith("✅"):
        return gr.skip(), message, gr.skip()
    return load_song_editor(selected_id)[2], message, choices


def load_song_editor(track_id):
    """Load editable metadata by stable ID, including legacy coverless songs."""
    try:
        track = Library().get(track_id) if track_id else None
        if track is None:
            return "", "", None
        description = track.cover_description or (
            f"Original {track.style} album artwork with a {track.mood} mood. "
            "Expressive imagery and colors; no lettering or logos."
        )
        return track.title, description, track.cover_path
    except LibraryError:
        raise gr.Error("Could not load song details. Please refresh the library.") from None


def rename_and_refresh(track_id, title):
    """Refresh labels and stop this browser's cached DJ playback after a rename."""
    message = rename_song(track_id, title)
    if not message.startswith("✅"):
        return (message, *(gr.skip() for _ in range(11)))
    songs, playlist = refresh_dj_songs()
    return (
        message, load_library()[0], refresh_saved_song_choices(track_id),
        songs, playlist, None, None, {"ids": [], "index": 0, "phase": None},
        "Your playlist is empty. Select songs above.",
        "Generate a new DJ introduction for the renamed song.",
        "DJ set stopped after renaming. Rebuild your playlist to continue.",
        select_saved_song(track_id)[1],
    )


def retry_cover(track_id):
    """Retry album art without generating a new song."""
    try:
        library = Library()
        track = library.get(track_id) if track_id else None

        if track is None:
            return None, "⚠️ Song not found in your library."

        if track.cover_path:
            return (
                track.cover_path,
                "✅ This song already has album artwork."
            )

        track = generate_cover(track)

        if not track.cover_path:
            return None, "⚠️ Cover generation returned no artwork."

        library.update(track_id, cover_path=track.cover_path)

        return (
            track.cover_path,
            f"✅ Album cover for '{track.title}' saved!"
        )

    except CoverGenerationError as error:
        return None, f"⚠️ Cover generation failed: {error}"

    except LibraryError as error:
        return None, f"⚠️ Could not save album cover: {error}"

    except Exception:
        return None, "⚠️ Could not generate album cover. Please retry."




def load_library():
    """Load saved songs and their album covers."""
    try:
        tracks = Library().list()

        covers = [
            (
                track.cover_path,
                track.title
            )
            for track in tracks
            if track.cover_path
        ]

        return covers, f"💿 You have {len(tracks)} saved song(s)."

    except LibraryError as error:
        return [], f"⚠️ Could not load library: {error}"




def select_library_song(evt: gr.SelectData):
    """Load the audio for the selected album cover."""
    try:
        tracks = [
            track for track in Library().list()
            if track.cover_path
        ]

        index = evt.index

        if not isinstance(index, int) or not 0 <= index < len(tracks):
            return None, "Please select an album cover.", None

        track = tracks[index]

        if not track.audio_path:
            return None, "⚠️ This song has no audio file.", track.id

        return (
            track.audio_path,
            f"🎵 Now selected: {track.title}", track.id
        )

    except (LibraryError, OSError):
        return None, "⚠️ Could not load the selected song.", None



def select_saved_song(track_id):
    """Play any saved song, even without album artwork."""
    try:
        track = Library().get(track_id) if track_id else None

        if track is None:
            return None, "⚠️ Please select a saved song."

        if not track.audio_path:
            return None, "⚠️ This song has no audio file."

        message = f"🎵 Now selected: {track.title}"

        if not track.cover_path:
            message += " (album cover pending)"

        return track.audio_path, message

    except LibraryError as error:
        return None, f"⚠️ Could not load song: {error}"


def refresh_saved_song_choices(selected_id=None):
    """Refresh all saved songs, including those without covers."""
    try:
        tracks = Library().list()

        choices = [
            (
                track.title + (
                    " (cover pending)"
                    if not track.cover_path else ""
                ),
                track.id
            )
            for track in tracks
        ]

        ids = [track.id for track in tracks]

        return gr.update(
            choices=choices,
            value=selected_id if selected_id in ids else None
        )

    except LibraryError:
        raise gr.Error(
            "Could not refresh saved songs."
        ) from None



def download_voice_url(url):
    """Download a public HTTPS MP3/WAV voice sample."""

    parts = urlsplit(url.strip())

    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise DJError("Please enter a public HTTPS audio URL.")

    try:
        if parts.port not in (None, 443):
            raise DJError("The URL must use standard HTTPS.")

        addresses = socket.getaddrinfo(
            parts.hostname, 443, type=socket.SOCK_STREAM
        )

        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global
            for item in addresses
        ):
            raise DJError("The URL must point to a public website.")

    except (OSError, ValueError):
        raise DJError("Could not validate the audio URL.") from None

    suffix = Path(parts.path).suffix.lower()

    if suffix not in (".mp3", ".wav"):
        raise DJError("The URL must end in .mp3 or .wav.")

    class NoRedirects(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = build_opener(ProxyHandler({}), NoRedirects())

    try:
        request = Request(
            url,
            headers={"User-Agent": "AI-Jukebox/1.0"}
        )

        with opener.open(request, timeout=15) as response:
            audio = response.read(10 * 1024 * 1024 + 1)

    except (URLError, OSError):
        raise DJError(
            "Could not download audio. Use a direct public file URL."
        ) from None

    if not audio or len(audio) > 10 * 1024 * 1024:
        raise DJError("Audio must be between 1 byte and 10 MB.")

    valid_wav = (
        len(audio) >= 12
        and audio[:4] == b"RIFF"
        and audio[8:12] == b"WAVE"
    )
    valid_mp3 = audio.startswith(b"ID3") or (
        len(audio) >= 2
        and audio[0] == 0xFF
        and (audio[1] & 0xE0) == 0xE0
    )

    if not (valid_wav or valid_mp3):
        raise DJError("The URL did not return valid MP3/WAV audio.")

    folder = Path("data/voice-refs")
    folder.mkdir(parents=True, exist_ok=True)

    destination = folder / f"{uuid4().hex}{suffix}"
    destination.write_bytes(audio)

    return str(destination)



def generate_dj_intro(track_id, voice_choice, voice_file, voice_url):
    """Generate song-specific DJ commentary and speech."""
    if not track_id:
        return None, "⚠️ Please select a song first."

    if voice_choice == "Custom Voice" and not (
        voice_file or (voice_url and voice_url.strip())
    ):
        return None, "⚠️ Please upload a voice file or enter an audio URL."




    try:
        library = Library()
        track = library.get(track_id)

        if track is None:
            return None, "⚠️ Song not found in your library."

        
        # Use the uploaded file first, or download from the URL.
        voice_ref = None

        if voice_choice == "Custom Voice":
            if voice_file:
                voice_ref = voice_file
            else:
                voice_ref = download_voice_url(voice_url.strip())

        # Qwen writes commentary specific to the selected song.
        commentary = commentary_for_track(track)


      

        audio_path = speak(
            commentary,
            voice_ref_path=voice_ref
        )

        # Save the DJ introduction with the correct song.
        library.update(track_id, expected_title=track.title,
                       dj_audio_path=audio_path, dj_commentary=commentary)

        return (
            audio_path,
            f"✅ Your AI DJ introduction for '{track.title}' is ready!"
        )

    except (DJError, LibraryError) as error:
        return None, f"⚠️ {error}"

    except Exception:
        return None, (
            "⚠️ DJ generation failed. Please try again."
        )




def import_demo_tracks():
    """Add the three bundled demo songs to the library."""
    try:
        sample_file = (
            Path(__file__).resolve().parent.parent
            / "assets" / "samples" / "samples.json"
        )

        with sample_file.open(encoding="utf-8") as file:
            samples = json.load(file)

        library = Library()

        for sample in samples:
            library.add(Track.from_dict(sample))

        return load_library()

    except (OSError, ValueError, TypeError, LibraryError):
        return [], "⚠️ Could not load the demo songs."



def preview_playlist(track_ids):
    """Show the selected songs in playlist order."""
    if not track_ids:
        return "Your playlist is empty. Select songs above."

    tracks = {
        track.id: track
        for track in Library().list()
    }

    lines = ["### 🎧 Your DJ Set"]

    for number, track_id in enumerate(track_ids, start=1):
        track = tracks.get(track_id)

        if track is None:
            return "⚠️ A selected song was not found."

        lines.append(
            f"{number}. **{track.title}** — {track.style} "
            f"| 🎙️ DJ Intro → 🎵 Song"
        )

    return "\n\n".join(lines)



def start_dj_set(track_ids):
    """Start the playlist with the first DJ introduction."""
    empty_state = {"ids": [], "index": 0, "phase": None}

    if not track_ids:
        return None, empty_state, "⚠️ Select at least one song."

    try:
        library = Library()

        for track_id in track_ids:
            track = library.get(track_id)

            if not track or not track.audio_path or not track.dj_audio_path:
                return (
                    None,
                    empty_state,
                    "⚠️ A selected song needs a DJ introduction."
                )

            if not (
                Path(track.audio_path).is_file()
                and Path(track.dj_audio_path).is_file()
            ):
                return None, empty_state, "⚠️ A playlist audio file is missing."

        first_track = library.get(track_ids[0])

        state = {
            "ids": list(track_ids),
            "index": 0,
            "phase": "speech"
        }

        return (
            first_track.dj_audio_path,
            state,
            f"🎙️ Now introducing: {first_track.title}"
        )

    except LibraryError as error:
        return None, empty_state, f"⚠️ {error}"


def advance_dj_set(state):
    """Play the next DJ intro or song when audio finishes."""
    empty_state = {"ids": [], "index": 0, "phase": None}

    if not state or not state.get("ids"):
        return None, empty_state, "Your DJ set has ended."

    ids = state["ids"]
    index = state["index"]
    phase = state["phase"]

    if phase == "speech":
        next_phase = "song"
    elif phase == "song":
        index += 1
        next_phase = "speech"
    else:
        return None, empty_state, "Your DJ set has ended."

    if index >= len(ids):
        return None, empty_state, "🎉 Your DJ set is complete!"

    try:
        track = Library().get(ids[index])

        if track is None:
            return None, empty_state, "⚠️ Song not found."

        if next_phase == "speech":
            audio_path = track.dj_audio_path
            message = f"🎙️ Now introducing: {track.title}"
        else:
            audio_path = track.audio_path
            message = f"🎵 Now playing: {track.title}"

        if not audio_path or not Path(audio_path).is_file():
            return None, empty_state, "⚠️ Audio file is missing."

        new_state = {
            "ids": ids,
            "index": index,
            "phase": next_phase
        }

        return audio_path, new_state, message

    except LibraryError as error:
        return None, empty_state, f"⚠️ {error}"




def skip_dj_track(state):
    """Skip the current track and introduce the next one."""
    empty_state = {"ids": [], "index": 0, "phase": None}

    if not state or not state.get("ids"):
        return None, empty_state, "No active DJ set."

    ids = state["ids"]
    next_index = state["index"] + 1

    if next_index >= len(ids):
        return None, empty_state, "🎉 Your DJ set is complete!"

    try:
        track = Library().get(ids[next_index])

        if (
            track is None
            or not track.dj_audio_path
            or not Path(track.dj_audio_path).is_file()
        ):
            return None, empty_state, "⚠️ Next DJ introduction is missing."

        new_state = {
            "ids": ids,
            "index": next_index,
            "phase": "speech"
        }

        return (
            track.dj_audio_path,
            new_state,
            f"⏭️ Skipped to: {track.title}"
        )

    except LibraryError as error:
        return None, empty_state, f"⚠️ {error}"




def refresh_dj_songs():
    """Refresh available songs and playable playlist tracks."""
    try:
        tracks = Library().list()

        song_choices = [
            (track.title, track.id)
            for track in tracks
        ]

        playlist_choices = [
            (f"{track.title} — {track.style}", track.id)
            for track in tracks
            if track.audio_path and track.dj_audio_path
        ]

        return (
            gr.update(choices=song_choices, value=None),
            gr.update(choices=playlist_choices, value=[])
        )

    except LibraryError:
        raise gr.Error("Could not refresh the song library.") from None




def build_app():
    """Build the AI Jukebox interface."""

    
    with gr.Blocks(
        title="AI Jukebox",
        theme=gr.themes.Soft(
    primary_hue="teal",
    neutral_hue="slate"

        ),
        css="""
        #library-gallery .grid-container {
            grid-template-columns: repeat(
                auto-fill, 200px
            ) !important;
            grid-auto-rows: 200px !important;
            justify-content: start !important;
            gap: 16px !important;
        }

        
        #library-gallery .caption-label {
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            max-width: 100% !important;
            box-sizing: border-box;
            padding: 8px 10px !important;
            border-radius: 0 0 10px 10px;
            background: rgba(15, 23, 42, 0.9) !important;
            color: #ffffff !important;
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        #jukebox-hero {
            background: linear-gradient(
                115deg,
                #0F172A 0%,
                #0F766E 60%,
                #14B8A6 100%
            );
            border-radius: 20px;
            padding: 36px 40px;
            margin-bottom: 24px;
            box-shadow: 0 8px 24px rgba(15, 118, 110, 0.15);
        }

        #jukebox-hero h1,
        #jukebox-hero p,
        #jukebox-hero strong {
            color: #FFFFFF !important;
        }
        
        #studio-controls,
        #studio-output,
        #dj-intro-panel,
        #dj-playlist-setup,
        #dj-playback-panel {
            background: var(--block-background-fill);
            border: 1px solid var(--block-border-color);
            border-radius: 18px;
            padding: 20px;
        }
        
        #dj-voice-settings {
            border: 1px solid #14B8A6 !important;
            border-radius: 12px !important;
            background: rgba(20, 184, 166, 0.10) !important;
            padding: 8px 12px;
        }

        
        #dj-song-picker,
        #dj-song-picker .wrap,
        #dj-song-picker .wrap-inner {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }

      
        #dj-song-picker .secondary-wrap {
            border: 1px solid #14B8A6 !important;
            border-radius: 12px !important;
            background: rgba(20, 184, 166, 0.10) !important;
            overflow: hidden;
        }

        #dj-song-picker .secondary-wrap:focus-within {
            border-color: #5EEAD4 !important;
        }

        
        /* Add breathing room below the song selector */
        #dj-song-picker {
            margin-bottom: 16px !important;
        }

        /* Align DJ Voice with Choose a Song */
        #dj-voice-choice,
        #dj-voice-choice .wrap {
            padding-left: 0 !important;
            padding-right: 0 !important;
        }

        /* Match the Generate button's text size */
        #dj-song-picker .block-label,
        #dj-voice-choice .block-label {
            font-size: 16px !important;
            font-weight: 700 !important;
        }
        
        #dj-song-label {
            margin-bottom: -8px !important;
        }

        #dj-song-label strong {
            display: inline-block;
            background: #0D9488;
            color: white !important;
            border-radius: 5px;
            padding: 4px 6px;
            font-size: 16px;
            font-weight: 700;
        }
        
        #dj-skip-button {
            max-width: 180px;
            margin-left: auto;
        }








        """


    ) as demo:

        
        gr.Markdown(
            "# 🎵 AI Jukebox\n\n"
            "**Your music. Your mood. Made with AI.**\n\n"
            "Create original songs, discover your sound, "
            "and let your personal AI DJ take over.",
            elem_id="jukebox-hero"
        )


        
        with gr.Tab("🎶 Create a Song"):
            gr.Markdown("## Create Your Next Hit")
            gr.Markdown(
                "Choose your style, set the mood, "
                "and let AI bring your song to life."
            )

            
            with gr.Row():
                # LEFT: Song creation settings
                with gr.Column(scale=2, elem_id="studio-controls"):
                    gr.Markdown("### 🎛️ Create Your Song")

                    style = gr.Dropdown(
                        choices=[
                            "Pop", "Rock", "Country", "Hip-Hop",
                            "Electronic", "Indie", "Jazz",
                            "R&B", "Synthwave"
                        ],
                        value="Pop",
                        label="Musical Style"
                    )

                    mood = gr.Dropdown(
                        choices=[
                            "Happy", "Energetic", "Relaxed",
                            "Romantic", "Sad", "Dreamy",
                            "Hopeful", "Mysterious"
                        ],
                        value="Happy",
                        label="Mood"
                    )

                    duration = gr.Slider(
                        minimum=30,
                        maximum=180,
                        value=60,
                        step=15,
                        label="Song Duration (seconds)"
                    )

                    vocal_mode = gr.Radio(
                        choices=["Vocals", "Instrumental"],
                        value="Vocals",
                        label="Song Type"
                    )

                    generate_btn = gr.Button(
                        "✨ Generate My Song",
                        variant="primary"
                    )

                    retry_btn = gr.Button(
                        "🔄 Retry Song Generation",
                        variant="secondary"
                    )

                # RIGHT: Generated music and artwork
                with gr.Column(scale=3, elem_id="studio-output"):
                    gr.Markdown("### 🎧 Your Music")

                    generation_status = gr.Markdown(
                        "Your song will appear here once generated."
                    )

                    cover_preview = gr.Image(
                        label="🎨 Your Album Cover",
                        type="filepath",
                        interactive=False,
                        height=300,
                        width=300
                    )

                    song_preview = gr.Audio(
                    elem_id="generated-song-player",
                        label="🎧 Your Generated Song",
                        interactive=False
                    )



            generate_btn.click(
                fn=create_song,
                inputs=[style, mood, duration, vocal_mode],
                outputs=[song_preview, cover_preview, generation_status],
                show_progress="full"
            )
            
            retry_btn.click(
                fn=create_song,
                inputs=[style, mood, duration, vocal_mode],
                outputs=[song_preview, cover_preview, generation_status],
                show_progress="full"
            )



        
        with gr.Tab("💿 My Library") as library_tab:
            gr.Markdown("## Your Music Collection")
            gr.Markdown(
                "All your AI-generated songs in one place."
            )

            
            with gr.Row():
                refresh_btn = gr.Button(
                    "🔄 Refresh Library",
                    variant="primary"
                )

                demo_btn = gr.Button(
                    "🎵 Load 3 Demo Songs",
                    variant="secondary"
                )


            library_status = gr.Markdown()

            
            
            library_gallery = gr.Gallery(
                label="Your Album Collection",
                columns=4,
                height=240,
                object_fit="cover",
                elem_id="library-gallery"
            )

            
            saved_song_dropdown = gr.Dropdown(
                choices=[
                    (
                        track.title + (
                            " (cover pending)"
                            if not track.cover_path else ""
                        ),
                        track.id
                    )
                    for track in Library().list()
                ],
                label="Choose Any Saved Song",
                info="Includes songs waiting for album artwork."
            )

            retry_cover_btn = gr.Button(
                "🎨 Retry Missing Album Cover",
                variant="secondary"
            )

            retry_cover_result = gr.State()
            regenerated_cover_result = gr.State()

            with gr.Accordion("Edit selected song", open=True):
                gr.Markdown(
                    "Choose a saved song above. Renaming keeps its audio and lyrics, "
                    "but clears its old DJ introduction and stops this browser's DJ set."
                )
                song_title = gr.Textbox(label="Song title", max_length=200)
                rename_btn = gr.Button("Save Song Title")
                editor_cover = gr.Image(label="Current album cover", type="filepath",
                                        interactive=False, height=240)
                cover_description = gr.Textbox(
                    label="Cover description", lines=3, max_length=2000,
                    info="Describe the replacement artwork. Uses FLUX; no image upload."
                )
                regenerate_btn = gr.Button("Regenerate Album Cover")
                edit_status = gr.Markdown()

            saved_song_dropdown.change(
                fn=load_song_editor, inputs=[saved_song_dropdown],
                outputs=[song_title, cover_description, editor_cover]
            )
            regenerate_btn.click(
                fn=regenerate_editor_cover, inputs=[saved_song_dropdown, cover_description],
                outputs=[regenerated_cover_result], api_name="regenerate_cover",
                concurrency_id="cover-edit", concurrency_limit=1
            ).then(
                fn=show_cover_result, inputs=[regenerated_cover_result, saved_song_dropdown],
                outputs=[editor_cover, edit_status, saved_song_dropdown], queue=False
            ).then(
                fn=load_library, inputs=[], outputs=[library_gallery, library_status]
            )


                
            

          
            demo_btn.click(
                fn=import_demo_tracks,
                inputs=[],
                outputs=[library_gallery, library_status]
            ).then(
                fn=refresh_saved_song_choices,
                inputs=[saved_song_dropdown],
                outputs=[saved_song_dropdown]
            )

            refresh_btn.click(
                fn=load_library,
                inputs=[],
                outputs=[library_gallery, library_status]
            ).then(
                fn=refresh_saved_song_choices,
                inputs=[saved_song_dropdown],
                outputs=[saved_song_dropdown]
            )


            
            
            
            library_tab.select(
                fn=load_library,
                inputs=[],
                outputs=[library_gallery, library_status]
            ).then(
                fn=refresh_saved_song_choices,
                inputs=[saved_song_dropdown],
                outputs=[saved_song_dropdown]
            )


            gr.Markdown("### 🎧 Listen to Your Music")

            selected_song_status = gr.Markdown(
                "Click an album cover above to select a song."
            )

            library_audio = gr.Audio(
                    elem_id="library-song-player",
                label="Selected Song",
                interactive=False
            )

            library_gallery.select(
                fn=select_library_song,
                inputs=[],
                outputs=[library_audio, selected_song_status, saved_song_dropdown]
            )

        
            saved_song_dropdown.change(
                fn=select_saved_song,
                inputs=[saved_song_dropdown],
                outputs=[library_audio, selected_song_status]
            )

            
            retry_cover_btn.click(
                fn=retry_editor_cover,
                inputs=[saved_song_dropdown],
                outputs=[retry_cover_result], api_name="retry_cover",
                concurrency_id="cover-edit", concurrency_limit=1
            ).then(
                fn=show_cover_result,
                inputs=[retry_cover_result, saved_song_dropdown],
                outputs=[editor_cover, edit_status, saved_song_dropdown], queue=False
            ).then(
                fn=load_library,
                inputs=[],
                outputs=[library_gallery, library_status]
            )




        
        with gr.Tab("🎙️ AI DJ"):
            gr.Markdown("## 🎙️ Meet Your AI DJ")
            gr.Markdown(
                "Choose a song and let your AI DJ introduce it!"
            )

            
            with gr.Column(elem_id="dj-intro-panel"):
                
                gr.Markdown(
                    "**Choose a Song**",
                    elem_id="dj-song-label"
                )

               


                dj_song = gr.Dropdown(
                    choices=[
                        (track.title, track.id)
                        for track in Library().list()
                    ],
                    label="Choose a Song",
                    show_label=False,
                    container=False,
                    elem_id="dj-song-picker"
                )


                
                dj_voice = gr.Radio(
                    choices=["Default Voice", "Custom Voice"],
                    value="Default Voice",
                    label="DJ Voice",
                    elem_id="dj-voice-choice"
                )


                
                with gr.Accordion(
                    "🎤 Custom DJ Voice — Click to Expand (Optional)",
                    open=False,
                    elem_id="dj-voice-settings"
                ):

                    dj_voice_reference = gr.File(
                        label="Upload Your Voice",
                        file_types=[".mp3", ".wav"],
                        type="filepath"
                    )

                    dj_voice_url = gr.Textbox(
                        label="🔗 Load Voice from URL",
                        placeholder="https://example.com/voice.wav",
                        info="Paste a direct HTTPS link to an MP3 or WAV recording."
                    )

                    gr.Markdown(
                        "Only upload a voice recording you own "
                        "or have permission to use."
                    )

                dj_generate_btn = gr.Button(
                    "🎤 Generate DJ Introduction",
                    variant="primary"
                )

                dj_status = gr.Markdown(
                    "Select a song to create its DJ introduction."
                )

                dj_audio = gr.Audio(
                    elem_id="dj-preview-player",
                    label="🎧 Your DJ Introduction",
                    interactive=False
                )

            
            gr.Markdown("## 🎶 Build Your DJ Playlist")
            gr.Markdown(
                "Select the songs you want your AI DJ to play. "
                "Only songs with completed DJ introductions appear here."
            )

            
            with gr.Column(elem_id="dj-playlist-setup"):
                playlist_selector = gr.Dropdown(
                    choices=[
                        (f"{track.title} — {track.style}", track.id)
                        for track in Library().list()
                        if track.audio_path and track.dj_audio_path
                    ],
                    multiselect=True,
                    label="Choose Your Playlist Songs",
                    info="Select multiple songs for your DJ set."
                )

                refresh_dj_btn = gr.Button(
                    "🔄 Refresh Available Songs"
                )

            
                playlist_preview = gr.Markdown(
                    "Your playlist is empty. Select songs above."
                )



            refresh_dj_btn.click(
                fn=refresh_dj_songs,
                inputs=[],
                outputs=[dj_song, playlist_selector]
            )


            

            playlist_selector.change(
                fn=preview_playlist,
                inputs=[playlist_selector],
                outputs=[playlist_preview]
            )
            
            playlist_state = gr.State(
                {"ids": [], "index": 0, "phase": None}
            )

            
            
            with gr.Column(elem_id="dj-playback-panel"):
                start_playlist_btn = gr.Button(
                    "▶️ Start DJ Set",
                    variant="primary"
                )

                playback_status = gr.Markdown(
                    "Your DJ set is ready when you are."
                )

                playlist_audio = gr.Audio(
                    elem_id="dj-playlist-player",
                    label="🎶 DJ Playlist Player",
                    interactive=False,
                    autoplay=True
                )

                skip_playlist_btn = gr.Button(
                    "⏭️ Skip to Next Song",
                    variant="secondary",
                    size="sm",
                    elem_id="dj-skip-button"
                )


            start_playlist_btn.click(
                fn=start_dj_set,
                inputs=[playlist_selector],
                outputs=[
                    playlist_audio,
                    playlist_state,
                    playback_status
                ]
            )


            skip_playlist_btn.click(
                fn=skip_dj_track,
                inputs=[playlist_state],
                outputs=[
                    playlist_audio,
                    playlist_state,
                    playback_status
                ]
            )

            
            playlist_audio.stop(
                fn=advance_dj_set,
                inputs=[playlist_state],
                outputs=[
                    playlist_audio,
                    playlist_state,
                    playback_status
                ],
                show_progress="hidden"
            )

            
           

           
           
 


         



            

            dj_generate_btn.click(
                fn=generate_dj_intro,
                inputs=[
                    dj_song,
                    dj_voice,
                    dj_voice_reference,
                    dj_voice_url
                ],
                outputs=[dj_audio, dj_status],
                show_progress="full"
            )


      
        rename_btn.click(
            fn=rename_and_refresh, inputs=[saved_song_dropdown, song_title],
            outputs=[edit_status, library_gallery, saved_song_dropdown, dj_song,
                     playlist_selector, dj_audio, playlist_audio, playlist_state,
                     playlist_preview, dj_status, playback_status, selected_song_status]
        )

        # Pause other players without clearing saved audio.
        for player, active_id in (
            (song_preview, "generated-song-player"),
            (library_audio, "library-song-player"),
            (dj_audio, "dj-preview-player"),
            (playlist_audio, "dj-playlist-player"),
        ):
            player.play(
                fn=None,
                inputs=[],
                outputs=[],
                js=f"""() => {{
                    function findDeep(root, id) {{
                        const match = root.getElementById?.(id);
                        if (match) return match;

                        for (const node of root.querySelectorAll("*")) {{
                            if (node.id === id) return node;
                            if (node.shadowRoot) {{
                                const found = findDeep(node.shadowRoot, id);
                                if (found) return found;
                            }}
                        }}
                        return null;
                    }}

                    function pauseDeep(root) {{
                        if (!root) return;

                        if (root.shadowRoot) {{
                            pauseDeep(root.shadowRoot);
                        }}

                        if (root instanceof HTMLMediaElement) {{
                            root.pause();
                        }}

                        for (const node of root.querySelectorAll("*")) {{
                            if (node instanceof HTMLMediaElement) {{
                                node.pause();
                            }}
                            if (node.shadowRoot) {{
                                pauseDeep(node.shadowRoot);
                            }}
                        }}
                    }}

                    for (const id of [
                        "generated-song-player",
                        "library-song-player",
                        "dj-preview-player",
                        "dj-playlist-player"
                    ]) {{
                        if (id !== "{active_id}") {{
                            pauseDeep(findDeep(document, id));
                        }}
                    }}
                }}""",
                queue=False
            )

            

    return demo


if __name__ == "__main__":
    build_app().launch()
