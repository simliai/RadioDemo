import threading
import websockets
import asyncio
import json
from queue import Empty, Queue
import numpy as np
import cv2
import time
import pyaudio
import requests

DisplayStarted = False

async def recv(
    frames: Queue, audio: asyncio.Queue, websocket: websockets.WebSocketClientProtocol
):
    try:
        while True:
            s = time.time()
            frame = await websocket.recv()
            print("TIME", time.time() - s)
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
                try:
                    f = frame[9 : 9 + int.from_bytes(frame[5:9], "little")]
                    f = np.frombuffer(f[12:], dtype=np.uint8)
                    f = cv2.imdecode(f, flags=1)
                    frames.put(f)
                    a = frame[18 + int.from_bytes(frame[5:9], "little") :]
                    await audio.put(a)
                except Exception as e:
                    print(e)
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

        while pcm.qsize() < 16:
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

def Display(frames: Queue):
    try:
        namedWindow = "Video"
        cv2.startWindowThread()
        cv2.namedWindow(namedWindow, cv2.WINDOW_NORMAL | cv2.WINDOW_AUTOSIZE | cv2.WINDOW_KEEPRATIO)
        while frames.qsize() < 16:
            cv2.imshow(namedWindow, np.zeros((512, 512, 3), dtype=np.uint8))
            time.sleep(0.001)
            print("waiting for frames")
        s = time.time()
        global DisplayStarted
        DisplayStarted = True
        while True:
            try:
                frame = frames.get()
            except Empty:
                continue
            if isinstance(frame, bool) and not frame:
                print("END")
                break
            elif isinstance(frame, np.ndarray):
                cv2.imshow(namedWindow, frame)
                cv2.waitKey(1)
                c = time.time()
                sleepTime = 1 / 30 - c + s
                if sleepTime > 0:
                    time.sleep(sleepTime)
                s = time.time()
    except Exception as e:
        print("DISPLAY ERROR", e)
        pass
    finally:
        print("DISPLAY DONE")

async def send(
    websocket: websockets.WebSocketClientProtocol, process: asyncio.subprocess.Process
):
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
    # Start a new session and get the session token
    metadata = {
        "video_reference_url": "https://storage.googleapis.com/charactervideos/5514e24d-6086-46a3-ace4-6a7264e5cb7c/5514e24d-6086-46a3-ace4-6a7264e5cb7c.mp4",
        "isJPG": True,
        "faceId": "tmp9i8bbq7c",
        "syncAudio": True,
        "apiKey": "9gunxygzoyl8txw6wb3hfd"  # Replace with your actual API key
    }
    response = requests.post("https://api.simli.ai/startAudioToVideoSession", json=metadata)
    response.raise_for_status()
    session_token = response.json()["session_token"]
    print("Received session: ", session_token)

    async with websockets.connect("wss://api.simli.ai/LipsyncStream") as websocket:
        await websocket.send(session_token)
        print("Sent session token")

        url = "https://radio.talksport.com/stream"

        ffmpeg = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            url,
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
        while frames.qsize() < 1:
            await asyncio.sleep(0.001)

        audioTask = asyncio.create_task(
            playAudio(
                audio,
                frames,
            )
        )
        await asyncio.gather(
            sendTask,
            recvTask,
        )
        await audioTask

def start_asyncio_loop(frames: Queue):
    asyncio.new_event_loop().run_until_complete(main(frames))

if __name__ == "__main__":
    frames = Queue()
    threading.Thread(target=start_asyncio_loop, daemon=True, args=(frames,)).start()
    while frames.qsize() < 16:
        time.sleep(0.001)
    Display(frames)
