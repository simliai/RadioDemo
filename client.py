import dis
import threading
import uvloop
import websockets
import asyncio
import json    
from queue import Empty, Queue
import numpy as np
import cv2
import time
import pyaudio


async def recv(frames : Queue, audio: asyncio.Queue, websocket: websockets.WebSocketClientProtocol):
    try:
        while True:
            # print("RECEIVING")
            frame = await websocket.recv()
            # print(len(frame))
            if frame == "DONE":
                print("DONE")
                frames.put(False)
                await audio.put(None)
                return
            if isinstance(frame,bytes) and  frame.startswith(b"ChunkStart"):
                print("CHUNK START" , int.from_bytes(frame[10:14], 'little'))
                frames.put(True)
                continue
            # frame = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), flags=1)
            if frame is not None and isinstance(frame, bytes) and len(frame)>0:
                # print("RECEIVED", len(frame))
                try:
                    f = frame[9:9+int.from_bytes(frame[5:9], 'little')]
                    f = np.frombuffer(f[12:], dtype=np.uint8)
                    f = cv2.imdecode(f, flags=1)
                    frames.put(f)
                    a = frame[18+int.from_bytes(frame[5:9], 'little'):]
                    await audio.put(a)
                    c = time.time()
                    s = c
                    # first = False
                    # print("received frame")
                except Exception as e:
                    print(e)
    except websockets.exceptions.ConnectionClosed as e:
        print("DISCONNECTED", e)

    except Exception as e:
        print("ENOF", e)
        pass
    frames.put(False)
    
async def playAudio(pcm : asyncio.Queue[bytes],frames: Queue):
    # with open("test.pcm", "wb") as f:
    try:
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        audio = pyaudio.PyAudio()
        def callback(in_data, frame_count, time_info, status):           
            try:
                data = pcm.get_nowait()
            except asyncio.QueueEmpty:
                data = b''
                # raise Exception("NO DATA")
            return (data, pyaudio.paContinue)

        while pcm.qsize()<8:
            # print("audioWaiting",pcm.qsize())
            await asyncio.sleep(1/30)
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, output=True,
                    frames_per_buffer=1024,
                    # stream_callback=callback
                    )

        displayTask = threading.Thread(target=Display, args=(frames,))
        displayTask.start()

        while True:
            s = time.time()
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
        displayTask.join()

def Display(frames : Queue):
    try:
        i = 0
        namedWindow = "Video"
        cv2.namedWindow(namedWindow, cv2.WINDOW_NORMAL)
        while frames.qsize()<8:
            cv2.imshow(namedWindow,np.zeros((512,512,3),dtype=np.uint8))
            time.sleep(1/30)
            print("waiting for frames")
        while True:
            s = time.time()
            try:
                frame = frames.get()
            except Empty as e:
                time.sleep(0.001)
                continue
            if isinstance(frame,bool) and not frame:
                print("END")
                break
            elif isinstance(frame, np.ndarray):
                # frame  =cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cv2.imshow(namedWindow,frame) # type: ignore
                cv2.waitKey(1)
                c = time.time()
                sleepTime = 1/30 - c + s
                if sleepTime > 1/30:
                    print(sleepTime)
                if sleepTime > 0:
                    time.sleep(sleepTime)

    except Exception as e:
        print("DISPLAY ERROR", e)
        pass
    finally:
        print("DISPLAY DONE")

async def send(websocket:websockets.WebSocketClientProtocol,process: asyncio.subprocess.Process):
    print("SENDING")
    while True:
        if process.stdout is None:
            print("NO STDOUT")
            break
        data = await process.stdout.read(4096)
        # print(len(data))
        await websocket.send(data)
    process.kill()
    await process.wait()

async def main():   
    async with websockets.connect("ws://127.0.0.1:8892/LipsyncStream") as websocket:
        metadata = {
            "video_reference_url": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.mp4",
            "face_det_results": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.pkl",
            "isSuperResolution": True,
            "isJPG": True,
            'syncAudio': True
        }
        await websocket.send(json.dumps(metadata))
        url = "https://radio.talksport.com/stream"
        ffmpeg = [
            "ffmpeg",
            '-nostdin',
            '-v',
            'error',
            "-i",
            url,
            "-f",
            's16le',
            "-acodec",
            "pcm_s16le",
            "-ar", 
            "16000",
            "-ac",
            "1",
            'pipe:1',
        ]
        print(" ".join(ffmpeg))
        process =  await asyncio.subprocess.create_subprocess_exec(
            *ffmpeg,
            stdout=asyncio.subprocess.PIPE,
            )
        print("FFMPEG STARTED")
        sendTask = asyncio.create_task(send(websocket,process))
        frames = Queue()
        audio = asyncio.Queue()
        print("sent metadata")
        recvTask = asyncio.create_task(recv(frames,audio,websocket))
        while frames.qsize()<8:
            await asyncio.sleep(1/30)
        audioTask = asyncio.create_task(playAudio(audio,frames,))
        await asyncio.gather(
sendTask, 
recvTask,
            )
        await audioTask
        

# uvloop.install()
asyncio.run(main())