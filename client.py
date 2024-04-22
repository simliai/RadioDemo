import threading
import websockets
import asyncio
import json    
from queue import Queue, Empty
import numpy as np
import cv2
import time

async def captureRadio(url:str):
    # ffmpeg = [
    #     "ffmpeg",
    #     '-nostdin',
    #     '-v',
    #     'debug',
    #     "-i",
    #     url,
    #     "-f",
    #     's16le',
    #     "-acodec",
    #     "pcm_s16le",
    #     "-ar", 
    #     "16000",
    #     "-ac",
    #     "1",
    #     'pipe:1',
    # ]
    print(" ".join(ffmpeg))
    try:
        process = await asyncio.create_subprocess_exec(*ffmpeg, stdout=asyncio.subprocess.PIPE)
        # process= await asyncio.create_subprocess_exec(*("ffmpeg -i https://radio.talksport.com/stream -f s16le -acodec pcm_s16le -ar 16000 -ac 1 pipe:1".split(" ")), stdout=asyncio.subprocess.PIPE)

    except Exception as e:
        print("FFMPEG ERROR", e)
        raise e
    while True:
        data = await process.stdout.read(1024)

        yield data
        
async def recv(frames : Queue, audio: asyncio.Queue, websocket: websockets.WebSocketClientProtocol):
    try:
        while True:
            print("RECEIVING")
            frame = await websocket.recv()
            print(len(frame))
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
                print("RECEIVED", len(frame))
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
                    print("received frame")
                except Exception as e:
                    print(e)
    except websockets.exceptions.ConnectionClosed as e:
        print("DISCONNECTED", e)

    except Exception as e:
        print("ENOF", e)
        pass
    frames.put(False)
    
async def playAudio(pcm : asyncio.Queue[bytes]):
    # with open("test.pcm", "wb") as f:
    try:
        i = 0
        pcmRemenants = b''
        while pcm.qsize()<17:
            # print("audioWaiting",pcm.qsize())
            time.sleep(1/30)
        ffplay = await asyncio.create_subprocess_exec("ffplay","-f","s16le","-ar","16000","-ac","1",'-acodec','pcm_s16le',"pipe:0",stdin=asyncio.subprocess.PIPE)
        while True:
            s = time.time()
            pcmBytes = await pcm.get()    
            if pcmBytes is None or not pcmBytes:
                print("END AUDIO")
                break
            # print(len(pcmBytes))
            # i = 0
            # for i in range(0,len(pcmBytes),320):
            #     vmic.write_frames(pcmBytes[i:i+320])
            # if i < len(pcmBytes):
            pcmBytes = pcmRemenants + pcmBytes
            cutOff = len(pcmBytes)//320*320
            if ffplay.stdin is not None:
                ffplay.stdin.write(pcmBytes[:cutOff])
                await ffplay.stdin.drain()
            # f.write(pcmBytes[:cutOff])
            pcmRemenants = pcmBytes[cutOff:]
            print(len(pcmBytes), len(pcmRemenants))
            # sleepTime= 1/30 - (time.time()-s)
            # print(sleepTime)
            # if sleepTime > 0:    
            #     time.sleep(sleepTime)
            
            # vmic.write_frames(pcmBytes[i+320:])
    except Exception as e:
        print("PLAY AUDIO ERROR", e)
        pass

def Display(frames : asyncio.Queue):
    pcmQueue = Queue()
    try:
        i = 0
        namedWindow = "Video"
        cv2.namedWindow(namedWindow, cv2.WINDOW_NORMAL)
        while frames.qsize()<17:
            cv2.imshow(namedWindow,np.zeros((512,512,3),dtype=np.uint8))
            time.sleep(1/30)
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
                frame  =cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cv2.imshow(frame) # type: ignore
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
        pcmQueue.put(None)
        print("DISPLAY DONE")

async def send(websocket:websockets.WebSocketClientProtocol,data:str):
    async for d in captureRadio(data):
        await websocket.send(d)
        print(len(d))

async def echo():   
    async with websockets.connect("ws://34.91.9.107:8892/LipsyncStream") as websocket:
        metadata = {
            "video_reference_url": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.mp4",
            "face_det_results": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.pkl",
            "isSuperResolution": True,
            "isJPG": True,
            'syncAudio': True
        }
        await websocket.send(json.dumps(metadata))
        sendTask = asyncio.create_task(send(websocket,"https://radio.talksport.com/stream"))
        frames = Queue()
        audio = asyncio.Queue()
        print("sent metadata")
        recvTask = asyncio.create_task(recv(frames,audio,websocket))
        # displayTask = threading.Thread(target = Display,args=(frames,))
        audioTask = asyncio.create_task(playAudio(audio,))
        # displayTask.start()
        await asyncio.gather(sendTask, recvTask,)
        # displayTask.join()
        
asyncio.run(echo())