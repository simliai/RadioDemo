import threading
import websockets
import asyncio
import json    
from queue import Queue, Empty
import numpy as np
import cv2
import time

import pyaudio


async def captureRadio(url: str):
    ffmpeg_cmd = [
        "ffmpeg",
        '-nostdin',
        '-v', 'debug',
        "-i", url,
        "-f", 's16le',
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        'pipe:1',
    ]
    print("Running FFmpeg command:", " ".join(ffmpeg_cmd))
    try:
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except Exception as e:
        print("Failed to start FFmpeg:", e)
        return

    while True:
        data = await process.stdout.read(1024)
        if not data:
            print("No more data received from FFmpeg")
            break
        print(f"Received {len(data)} bytes from FFmpeg")
        yield data

    # Check for errors in stderr
    stderr_output = await process.stderr.read()
    if stderr_output:
        print("FFmpeg error output:", stderr_output.decode())

        
async def recv(frames: Queue, audio: asyncio.Queue, websocket: websockets.WebSocketClientProtocol):
    try:
        while True:
            print("Waiting for data...")
            frame = await websocket.recv()  # Receives data from WebSocket
            print(f"Received data: {len(frame) if isinstance(frame, bytes) else 'non-bytes data'}")  # Log the received data size

            # Check if the session should end
            if frame == "DONE":
                print("DONE received, stopping reception.")
                frames.put(False)  # Signal to other components that reception is done
                await audio.put(None)  # Signal to audio processing that no more data will be sent
                return

            # Example of handling specific data formats
            if isinstance(frame, bytes):
                if frame.startswith(b"ChunkStart"):  # Check if this is a new chunk
                    chunk_size = int.from_bytes(frame[10:14], 'little')
                    print("New chunk starting, size:", chunk_size)
                    frames.put(True)  # Placeholder for actual frame handling
                    continue

                # Assume the frame contains image data
                # Example processing - adapt as necessary
                try:
                    f = frame[9:9 + int.from_bytes(frame[5:9], 'little')]
                    f = np.frombuffer(f[12:], dtype=np.uint8)
                    f = cv2.imdecode(f, flags=1)
                    frames.put(f)
                    a = frame[18 + int.from_bytes(frame[5:9], 'little'):]
                    await audio.put(a)
                    print("Processed frame and audio.")
                except Exception as e:
                    print(f"Error processing frame: {e}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"WebSocket disconnected: {e}")
    except Exception as e:
        print(f"Error during WebSocket communication: {e}")
    finally:
        frames.put(False)  # Ensure other components know reception has ended

    
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
        print(len(d))
        await websocket.send(d)
        print(len(d))


# async def main():
#     async with websockets.connect("ws://34.91.9.107:8892/LipsyncStream") as websocket:
#         metadata = {
#             "video_reference_url": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.mp4",
#             "face_det_results": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.pkl",
#             "isSuperResolution": True,
#             "isJPG": True,
#             'syncAudio': True
#         }
#         frames = Queue()
#         audio = asyncio.Queue()
#         await websocket.send(json.dumps(metadata))
#         sendTask = asyncio.create_task(send(websocket, "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"))
#         recvTask = asyncio.create_task(recv(frames, audio, websocket))
#         try:
#             await asyncio.wait([sendTask, recvTask], timeout=60)  # Wait for 60 seconds
#         except asyncio.TimeoutError:
#             print("Operation timed out")
#         finally:
#             sendTask.cancel()
#             recvTask.cancel()

# asyncio.run(main())


# Setup audio playback
def setup_audio_stream():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    output=True)
    return stream

# Function to play audio chunks
async def play_audio(audio_queue: asyncio.Queue, stream):
    try:
        while True:
            audio_chunk = await audio_queue.get()
            if audio_chunk is None:  # Use None as a signal to stop.
                break
            stream.write(audio_chunk)
    finally:
        stream.stop_stream()
        stream.close()

# Function to display video frames
def display_video(frames_queue: Queue):
    cv2.namedWindow("Video", cv2.WINDOW_NORMAL)
    while True:
        frame = frames_queue.get()
        if frame is False:  # Use False as a signal to stop.
            break
        cv2.imshow("Video", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):  # Press 'q' to quit the display
            break
    cv2.destroyAllWindows()

async def main():
    async with websockets.connect("ws://34.91.9.107:8892/LipsyncStream") as websocket:
        metadata = {
            "video_reference_url": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.mp4",
            "face_det_results": "https://storage.googleapis.com/charactervideos/tmp9i8bbq7c/tmp9i8bbq7c.pkl",
            "isSuperResolution": True,
            "isJPG": True,
            'syncAudio': True
        }
        await websocket.send(json.dumps(metadata))

        frames = Queue()
        audio = asyncio.Queue()

        # Set up audio stream
        audio_stream = setup_audio_stream()

        # Create tasks for sending and receiving data
        send_task = asyncio.create_task(send(websocket, "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"))
        recv_task = asyncio.create_task(recv(frames, audio, websocket))
        audio_task = asyncio.create_task(play_audio(audio, audio_stream))

        # Start video display in a separate thread
        video_thread = threading.Thread(target=display_video, args=(frames,))
        video_thread.start()

        try:
            # Wait for the WebSocket communication tasks with a timeout
            await asyncio.wait([send_task, recv_task, audio_task], timeout=60)
        except asyncio.TimeoutError:
            print("Operation timed out")
        finally:
            send_task.cancel()
            recv_task.cancel()
            audio_task.cancel()

        video_thread.join()  # Ensure the video thread is cleanly stopped

asyncio.run(main())