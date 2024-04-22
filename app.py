from fastapi import FastAPI , WebSocket, WebSocketDisconnect
import granian
from granian import Granian
from granian.constants import Interfaces
import asyncio
app = FastAPI()

@app.websocket("/echo")
async def echo(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_bytes()
            await websocket.send_bytes(data)
            print(len(data))
        except WebSocketDisconnect:
            break

if __name__ == "__main__":
    Granian("app:app",interface=Interfaces.ASGI,port=10100,).serve()