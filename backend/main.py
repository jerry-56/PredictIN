import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routes.auth import router as auth_router
from routes.wallet import router as wallet_router
from routes.markets import router as markets_router
from routes.orders import router as orders_router
from routes.admin import router as admin_router, start_scheduler
from websocket_manager import manager

load_dotenv()

app = FastAPI(
    title="PredictIN API",
    description="Prediction market platform with INR — Powered by FastAPI + Supabase",
    version="1.0.0",
)

# CORS — allow Vite dev server and production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(wallet_router)
app.include_router(markets_router)
app.include_router(orders_router)
app.include_router(admin_router)


@app.on_event("startup")
async def startup():
    start_scheduler()   # Cricket auto-resolution cron


@app.get("/")
async def root():
    return {"message": "PredictIN API is running 🚀", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── WebSocket endpoint for real-time market odds ──────────────────────────────

@app.websocket("/ws/market/{market_id}")
async def market_ws(websocket: WebSocket, market_id: str):
    await manager.connect_to_market(market_id, websocket)
    try:
        while True:
            await websocket.receive_text()   # keep-alive ping from client
    except WebSocketDisconnect:
        manager.disconnect_from_market(market_id, websocket)


@app.websocket("/ws/global")
async def global_ws(websocket: WebSocket):
    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_global(websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
