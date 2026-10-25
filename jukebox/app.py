
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
            gr.Markdown("Create your own AI-generated music.")

        with gr.Tab("💿 My Library"):
            gr.Markdown("Your songs and album artwork will appear here.")

        with gr.Tab("🎙️ AI DJ"):
            gr.Markdown("Customize your DJ and play your collection.")

    return demo


if __name__ == "__main__":
    build_app().launch()
