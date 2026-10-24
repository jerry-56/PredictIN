import os
import uvicorn
from main import app

# If running on Hugging Face Spaces with Gradio SDK, mount a status dashboard
try:
    import gradio as gr

    with gr.Blocks(title="PredictIN Backend") as demo:
        gr.Markdown("# 🏏 PredictIN API Server")
        gr.Markdown("Real-time Prediction Market API with Decentro UPI payment gateway.")
        gr.Markdown("### Quick Links")
        gr.Markdown("- **Interactive API Documentation:** [/docs](/docs)")
        gr.Markdown("- **Alternative OpenAPI Docs:** [/redoc](/redoc)")
        gr.Markdown("- **Health Endpoint:** [/health](/health)")
        gr.Markdown("- **Decentro Callback Webhook:** `/api/wallet/decentro/callback`")

    app = gr.mount_gradio_app(app, demo, path="/ui")
except ImportError:
    pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

