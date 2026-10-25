
import gradio as gr


def build_app():
    """Build the AI Jukebox interface."""

    with gr.Blocks(
        title="AI Jukebox",
        theme=gr.themes.Soft(
            primary_hue="violet",
            neutral_hue="slate"
        )
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


        with gr.Tab("💿 My Library"):
            gr.Markdown("Your songs and album artwork will appear here.")

        with gr.Tab("🎙️ AI DJ"):
            gr.Markdown("Customize your DJ and play your collection.")

    return demo


if __name__ == "__main__":
    build_app().launch()
