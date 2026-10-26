
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

    try:
        track = generate_cover(track)

    except CoverGenerationError as error:
        return (
            track.audio_path,
            None,
            f"⚠️ Your song is ready, but the cover failed: {error}"
        )

    except Exception:
        return (
            track.audio_path,
            None,
            "⚠️ Your song is ready, but cover art failed."
        )

    
    try:
        Library().add(track)

    except LibraryError as error:
        return (
            track.audio_path,
            track.cover_path,
            f"⚠️ Song and cover created, but saving failed: {error}"
        )

    return (
        track.audio_path,
        track.cover_path,
        f"✅ '{track.title}' and its cover were saved to your library!"
    )

    





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
            return None, "Please select an album cover."

        track = tracks[index]

        if not track.audio_path:
            return None, "⚠️ This song has no audio file."

        return (
            track.audio_path,
            f"🎵 Now selected: {track.title}"
        )

    except (LibraryError, OSError):
        return None, "⚠️ Could not load the selected song."


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
        track.dj_audio_path = audio_path
        library.add(track)

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
        #dj-intro-panel {
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

                
            

          
            demo_btn.click(
                fn=import_demo_tracks,
                inputs=[],
                outputs=[library_gallery, library_status]
            )
  

            refresh_btn.click(
                fn=load_library,
                inputs=[],
                outputs=[library_gallery, library_status]
            )

            library_tab.select(
                fn=load_library,
                inputs=[],
                outputs=[library_gallery, library_status]
            )

            gr.Markdown("### 🎧 Listen to Your Music")

            selected_song_status = gr.Markdown(
                "Click an album cover above to select a song."
            )

            library_audio = gr.Audio(
                label="Selected Song",
                interactive=False
            )

            library_gallery.select(
                fn=select_library_song,
                inputs=[],
                outputs=[library_audio, selected_song_status]
            )


        
        with gr.Tab("🎙️ AI DJ"):
            gr.Markdown("## 🎙️ Meet Your AI DJ")
            gr.Markdown(
                "Choose a song and let your AI DJ introduce it!"
            )

            
            with gr.Column(elem_id="dj-intro-panel"):
                dj_song = gr.Dropdown(
                    choices=[
                        (track.title, track.id)
                        for track in Library().list()
                    ],
                    label="Choose a Song",
                    elem_id="dj-song-picker"
                )

                dj_voice = gr.Radio(
                    choices=["Default Voice", "Custom Voice"],
                    value="Default Voice",
                    label="DJ Voice"
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
                    label="🎧 Your DJ Introduction",
                    interactive=False
                )

            
            gr.Markdown("## 🎶 Build Your DJ Playlist")
            gr.Markdown(
                "Select the songs you want your AI DJ to play. "
                "Only songs with completed DJ introductions appear here."
            )

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

            refresh_dj_btn.click(
                fn=refresh_dj_songs,
                inputs=[],
                outputs=[dj_song, playlist_selector]
            )


            playlist_preview = gr.Markdown(
                "Your playlist is empty. Select songs above."
            )

            playlist_selector.change(
                fn=preview_playlist,
                inputs=[playlist_selector],
                outputs=[playlist_preview]
            )
            
            playlist_state = gr.State(
                {"ids": [], "index": 0, "phase": None}
            )

            start_playlist_btn = gr.Button(
                "▶️ Start DJ Set",
                variant="primary"
            )

            playback_status = gr.Markdown(
                "Your DJ set is ready when you are."
            )

            playlist_audio = gr.Audio(
                label="🎶 DJ Playlist Player",
                interactive=False,
                autoplay=True
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
            
            skip_playlist_btn = gr.Button(
                "⏭️ Skip Song"
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


    return demo


if __name__ == "__main__":
    build_app().launch()
