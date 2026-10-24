from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import asyncio


class ConnectionManager:
    """Manages WebSocket connections per market room and global."""

    def __init__(self):
        # market_id -> list of connected websockets
        self.market_rooms: Dict[str, List[WebSocket]] = {}
        # Global connections (for admin broadcasts etc.)
        self.global_connections: List[WebSocket] = []

    async def connect_to_market(self, market_id: str, websocket: WebSocket):
        await websocket.accept()
        if market_id not in self.market_rooms:
            self.market_rooms[market_id] = []
        self.market_rooms[market_id].append(websocket)

    def disconnect_from_market(self, market_id: str, websocket: WebSocket):
        if market_id in self.market_rooms:
            self.market_rooms[market_id].remove(websocket)

    async def broadcast_to_market(self, market_id: str, message: str):
        if market_id in self.market_rooms:
            dead = []
            for ws in self.market_rooms[market_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.market_rooms[market_id].remove(ws)

    async def broadcast(self, message: str):
        """Broadcast to all global connections."""
        dead = []
        for ws in self.global_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.global_connections.remove(ws)

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.append(websocket)

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)


manager = ConnectionManager()
