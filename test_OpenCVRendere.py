import threading
import websockets
import asyncio
import json
from queue import Queue
import numpy as np
import cv2
import time
import pyaudio

DisplayStarted = False

async def recv(frames: Queue, audio: asyncio.Queue, websocket: websockets.WebSocketClientProtocol):
    try:
        while True:
            s = time.time()
            frame = await websocket.recv()
            if frame == "DONE":
                print("DONE")
                frames.put(False)
                await audio.put(None)
                return
            if isinstance(frame, bytes) and frame.startswith(b"ChunkStart"):
                print("CHUNK START", int.from_bytes(frame[10:14], "little"))
                frames.put(True)
                continue
            if frame is not None and isinstance(frame, bytes) and len(frame) > 0:
                f = frame[9 : 9 + int.from_bytes(frame[5:9], "little")]
                f = np.frombuffer(f[12:], dtype=np.uint8)
                f = cv2.imdecode(f, flags=1)
                frames.put(f)
                a = frame[18 + int.from_bytes(frame[5:9], "little") :]
                await audio.put(a)
            print("TIME", time.time()-s)
    except websockets.exceptions.ConnectionClosed as e:
        print("DISCONNECTED", e)

    except Exception as e:
        print("ENOF", e)
        pass
    frames.put(False)


async def playAudio(pcm: asyncio.Queue[bytes], frames: Queue):
    try:
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        audio = pyaudio.PyAudio()

        while pcm.qsize() < 17:
            await asyncio.sleep(0.001)
        
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=1024,
        )

        while True:
            pcmBytes = await pcm.get()
            if pcmBytes is None or not pcmBytes:
                print("END AUDIO")
                break

            if stream.is_active():
                stream.write(pcmBytes)

    except Exception as e:
        print("PLAY AUDIO ERROR", e)
        pass
    finally:
        try:
            displayTask.join()  # type: ignore
        except NameError:
            pass


async def send(websocket: websockets.WebSocketClientProtocol, process: asyncio.subprocess.Process):
    print("SENDING")
    while True:
        if process.stdout is None:
            print("NO STDOUT")
            break
        data = await process.stdout.read(4096)
        await websocket.send(data)
    process.kill()
    await process.wait()


async def main(frames: Queue):
    async with websockets.connect("ws://api.simli.ai/LipsyncStream") as websocket:
        metadata = {
            "video_reference_url": "https://storage.googleapis.com/charactervideos/5514e24d-6086-46a3-ace4-6a7264e5cb7c/5514e24d-6086-46a3-ace4-6a7264e5cb7c.mp4",
            "face_det_results": "https://storage.googleapis.com/charactervideos/5514e24d-6086-46a3-ace4-6a7264e5cb7c/5514e24d-6086-46a3-ace4-6a7264e5cb7c.pkl",
            "isSuperResolution": True,
            "isJPG": True,
            "syncAudio": True,
        }
        await websocket.send(json.dumps(metadata))
        url = "https://radio.talksport.com/stream"
        ffmpeg = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i", url,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "pipe:1",
        ]
        print(" ".join(ffmpeg))
        process = await asyncio.subprocess.create_subprocess_exec(
            *ffmpeg,
            stdout=asyncio.subprocess.PIPE,
        )
        print("FFMPEG STARTED")
        sendTask = asyncio.create_task(send(websocket, process))
        audio = asyncio.Queue()
        print("sent metadata")
        recvTask = asyncio.create_task(recv(frames, audio, websocket))
        audioTask = asyncio.create_task(
            playAudio(audio, frames)
        )
        await asyncio.gather(recvTask, audioTask)
    # asyncio.run(main())

def start_asyncio_loop(frames: Queue):
    asyncio.new_event_loop().run_until_complete(main(frames))

if __name__ == "__main__":
    frames = Queue()
    threading.Thread(target=start_asyncio_loop, daemon=True, args=(frames,)).start()
    cv2.imshow("Video", np.zeros((512, 512, 3), dtype=np.uint8))
    cv2.waitKey(1)
    while True:
        try:
            frame = frames.get()
            if isinstance(frame, bool) and not frame:
                print("END")
                break
            elif isinstance(frame, np.ndarray):
                cv2.imshow("Video", frame)
                cv2.waitKey(1)
        except Exception as e:
            print("DISPLAY ERROR", e)
            pass
    cv2.destroyAllWindows()