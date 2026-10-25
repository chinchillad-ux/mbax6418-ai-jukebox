
import gradio as gr

from jukebox.music import generate_song, SongGenerationError

from jukebox.cover import generate_cover, CoverGenerationError

from jukebox.library import Library, LibraryError


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
                f"{track.title} | {track.style} | {track.mood}"
            )
            for track in tracks
            if track.cover_path
        ]

        return covers, f"💿 You have {len(tracks)} saved song(s)."

    except LibraryError as error:
        return [], f"⚠️ Could not load library: {error}"






def build_app():
    """Build the AI Jukebox interface."""

    
    with gr.Blocks(
        title="AI Jukebox",
        theme=gr.themes.Soft(
            primary_hue="violet",
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
        """
    ) as demo:

    ) as demo:

        gr.Markdown(
            "# 🎵 AI Jukebox\n"
            "Create original music, build your collection, "
            "and let your AI DJ take over."
        )

        
        with gr.Tab("🎶 Create a Song"):
            gr.Markdown("## Create Your Next Hit")
            gr.Markdown(
                "Choose your style, set the mood, "
                "and let AI bring your song to life."
            )

            with gr.Row():
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

            generation_status = gr.Markdown(
                "Your song will appear here once generated."
            )

        
            cover_preview = gr.Image(
                label="🎨 Your Album Cover",
                type="filepath",
                interactive=False,
                height=350
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



        
        with gr.Tab("💿 My Library") as library_tab:
            gr.Markdown("## Your Music Collection")
            gr.Markdown(
                "All your AI-generated songs in one place."
            )

            refresh_btn = gr.Button("🔄 Refresh Library")

            library_status = gr.Markdown()

            
            
            library_gallery = gr.Gallery(
                label="Your Album Collection",
                columns=4,
                height=320,
                object_fit="cover",
                elem_id="library-gallery"
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


        with gr.Tab("🎙️ AI DJ"):
            gr.Markdown("Customize your DJ and play your collection.")

    return demo


if __name__ == "__main__":
    build_app().launch()
