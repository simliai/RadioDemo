import asyncio
import cv2
import numpy as np
import pyaudio
from queue import Queue, Empty
import websockets
import json
import time

async def video_and_audio_processing(websocket, frames_queue, audio_queue):
    cv2.namedWindow("Video", cv2.WINDOW_NORMAL | cv2.WINDOW_AUTOSIZE | cv2.WINDOW_KEEPRATIO)
    pyaudio_obj = pyaudio.PyAudio()
    stream = pyaudio_obj.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True, frames_per_buffer=1024)
    
    while True:
        try:
            frame = frames_queue.get_nowait()
            if frame is False:
                break
            elif isinstance(frame, np.ndarray):
                cv2.imshow("Video", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            audio_chunk = await audio_queue.get()
            if audio_chunk is None:
                break
            stream.write(audio_chunk)
            
        except Empty:
            await asyncio.sleep(0.01)  # Adjust the sleep time if needed for synchronization

    cv2.destroyAllWindows()
    stream.stop_stream()
    stream.close()
    pyaudio_obj.terminate()

async def recv(frames_queue, audio_queue, websocket):
    while True:
        frame = await websocket.recv()
        if frame == "DONE":
            frames_queue.put(False)
            await audio_queue.put(None)
            return
        # Parse your frames and audio data here. Assuming they are already separated
        # Below is a stub that needs to be replaced with your specific parsing logic
        if isinstance(frame, bytes) and len(frame) > 0:
            try:
                f = np.frombuffer(frame, dtype=np.uint8)
                f = cv2.imdecode(f, flags=1)
                frames_queue.put(f)
            except Exception as e:
                print(f"Error decoding frame: {e}")

            audio_chunk = b""  # Stub for audio chunk
            await audio_queue.put(audio_chunk)

async def main():
    frames_queue = Queue()
    audio_queue = asyncio.Queue()
    async with websockets.connect("ws://api.simli.ai/LipsyncStream") as websocket:
        metadata = {
            "video_reference_url": "https://storage.googleapis.com/charactervideos/5514e24d-6086-46a3-ace4-6a7264e5cb7c/5514e24d-6086-46a3-ace4-6a7264e5cb7c.mp4",
            "face_det_results": "https://storage.googleapis.com/charactervideos/5514e24d-6086-46a3-ace4-6a7264e5cb7c/5514e24d-6086-46a3-ace4-6a7264e5cb7c.pkl",
            "isSuperResolution": True,
            "isJPG": True,
            "syncAudio": True,
        }
        await websocket.send(json.dumps(metadata))
        
        # Create tasks for receiving/sending data
        recv_task = asyncio.create_task(recv(frames_queue, audio_queue, websocket))
        process_task = asyncio.create_task(video_and_audio_processing(websocket, frames_queue, audio_queue))

        await asyncio.gather(recv_task, process_task)

if __name__ == "__main__":
    asyncio.run(main())
