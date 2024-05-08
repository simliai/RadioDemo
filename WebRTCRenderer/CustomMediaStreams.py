import asyncio
import json
import time
from typing import Optional
import resampy
import numpy as np
import cv2
from aiortc import MediaStreamTrack, AudioStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame # type: ignore
from av import AudioFrame # type: ignore
import websockets
import fractions

class WSVideoTrack(MediaStreamTrack):
    kind = "video"
    def __init__(self):
        super().__init__()
        self.frameQueue:asyncio.Queue[bytes] = asyncio.Queue()
        self.currentTime = 0
        self.start=  time.time()

    async def recv(self):
        # print("recv called")
        try:
            self.start = time.time()
            frame = await self.frameQueue.get()
            if frame is None:
                raise MediaStreamError()
            frame = np.frombuffer(frame[12:], dtype=np.uint8)
            frame = cv2.imdecode(frame, flags=1)
            
            new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            new_frame.pts = self.currentTime
            self.currentTime += int(1/30 * 90000)
            new_frame.time_base = fractions.Fraction(1, 90000)
            sleepTime = 1/30-time.time()+self.start
            if sleepTime > 0:
                await asyncio.sleep(sleepTime)
            #     print("Video Sleeping", sleepTime)
            # else:
            #     print("Video NOT Sleeping", sleepTime)
            return new_frame
        except Exception:
            import traceback
            traceback.print_exc()

class WSAudioTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self):
        super().__init__()
        self.frameQueue:asyncio.Queue[bytes] = asyncio.Queue()
        self.timeStamp = 0
        self.timeBase = fractions.Fraction(1,16000)
        self.sampleRate = 16000
        self.start = time.time()
        self.first = True
        self.dump = open("dump.pcm", "wb")

    async def recv(self):
        try:
            s = time.time()
            audio = await self.frameQueue.get()
            if audio is None:
                raise MediaStreamError()
            # print(len(audio))
            audio = np.frombuffer(audio, dtype=np.int16)
            self.start = time.time()
            if self.first:
                print("Time till audio is received", time.time()-self.start)
                print("Time waiting for first chunk", time.time()-s)
                self.first = False
            audio = audio.reshape(1,-1)
            frame = AudioFrame.from_ndarray(audio, format="s16", layout="mono")
            frame.sample_rate = 16000
            frame.pts = self.timeStamp +1
            self.timeStamp += audio.shape[1]
            # print(audio.shape)
            frame.sample_rate = self.sampleRate
            frame.time_base = self.timeBase
            self.dump.write(audio.tobytes())
            sleepTime = 1/30-time.time()+self.start
            if sleepTime > 0:
                await asyncio.sleep(sleepTime)
            return frame
            
        except Exception:
            import traceback
            traceback.print_exc()


    def __del__(self):
        self.dump.close()

class WebSocketReceiver(MediaStreamTrack):
    def __init__(self, url:str, metadata:str):
        self.metadata = metadata
        self.url = url
        self.Run = True
        self.VideoStream = WSVideoTrack()
        self.AudioStream = WSAudioTrack()
        self.AudioStreamIn: Optional[AudioStreamTrack] = None
        self.sentStamp = 0
        
    async def Config(self):
        self.ws:websockets.WebSocketClientProtocol = await websockets.connect(self.url)
        await self.ws.send(self.metadata)
        self.first=  True
        return self.ws
    
    async def populateQueue(self):
        count = 0
        reportLatencyCount = 10
        while self.Run:
            data = await self.ws.recv()
            if data == "DONE":
                print("DONE")
                await self.VideoStream.frameQueue.put(None) # type: ignore
                await self.AudioStream.frameQueue.put(None) # type: ignore
                return
            if data is not None and isinstance(data, bytes):
                try:
                    f = data[9 : 9 + int.from_bytes(data[5:9], "little")]
                    await self.VideoStream.frameQueue.put(f)
                    a = data[18 + int.from_bytes(data[5:9], "little") :]
                    await self.AudioStream.frameQueue.put(a)
                    if count < reportLatencyCount:
                        # print("Audio Queue Size:", self.AudioStream.frameQueue.qsize())
                        print("Latency:", time.time()-self.sentStamp)
                        count += 1
                except Exception:
                    import traceback
                    traceback.print_exc()
        
    async def recv(self):
        if not self.Run:
            raise MediaStreamError()
        internalBuffer = []
        if self.AudioStreamIn is None:
            print("Input Stream Not Configured")
            return 
        if not hasattr(self,'dumper'):
            self.dumper = open("dumper.pcm", "wb")
        # while self.Run:
        if self.ws.open:
            if self.first:
                self.sentStamp = time.time()
            try:
                print("Waiting for Audio Stream")
                data = await self.AudioStreamIn.recv()
                print("RECEVIED")
            except Exception as e:
                self.dumper.close()
                raise Exception("Error in Audio Stream", e)
                # break
                return
            if self.first:
                print("Time till audio is received", time.time()-self.sentStamp)
            ogSampleRate:int = data.sample_rate
            print(ogSampleRate)
            datanp:np.ndarray = data.to_ndarray().astype(np.float32)
            datanp = datanp.flatten()
            try:
                datanp = resampy.resample(datanp, sr_orig= ogSampleRate, sr_new= 16000)
            except Exception as e:
                print("Error in resampling", e)
                raise MediaStreamError()
            datanp = (datanp).astype(np.int16)
            databytes = datanp[::2].tobytes()
            if self.first:
                print("Time till audio is processed", time.time()-self.sentStamp)
                self.first = False
            # print(len(databytes))
            internalBuffer.append(databytes)
            # if len(internalBuffer) < 10:
            #     continue
            self.dumper.write(b''.join(internalBuffer))
            await self.ws.send(b''.join(internalBuffer))
            internalBuffer = []
            return data
        else:
            print("Connection is closed")
        # self.dumper.close()

    def start(self):
        # self.ReceiveTask = asyncio.create_task(self.recv())
        self.SendTask = asyncio.create_task(self.populateQueue())

    async def GetStreams(self):
        return self.VideoStream, self.AudioStream
    
    async def Exit(self):
        self.Run = False
        await self.ws.send(b"DONE")
        await self.ws.close()
        # await self.ReceiveTask
        await self.SendTask

class EchoTrack(MediaStreamTrack):
    """
    A media stream track that reflects the same media frame it receives.
    """

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track
        self.kind = track.kind

    async def recv(self):
        s = time.time()
        frame = await self.track.recv()
        print("Latency:", time.time()-s)
        if self.track.kind == "audio":
            print(frame.sample_rate)
        return frame


class WSRadio:
    
    async def Config(self,metadata:dict):
        self.Run = True
        self.url = "https://radio.talksport.com/stream"
        self.ffmpeg = [
            "ffmpeg",
            '-nostdin',
            '-v',
            'error',
            "-i",
            self.url,
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
        self.process = await asyncio.subprocess.create_subprocess_exec(
            *self.ffmpeg,
            stdout=asyncio.subprocess.PIPE,
            )
        self.websocket = await websockets.connect("ws://34.91.9.107:8892/LipsyncStream")
        self.sendTask = asyncio.create_task(self.send())
        self.audioTrack = WSAudioTrack()
        self.videoTrack = WSVideoTrack()
        self.frames = self.videoTrack.frameQueue
        self.audio = self.audioTrack.frameQueue
        print("sent metadata")
        self.recvTask = asyncio.create_task(self.recv())
        await self.websocket.send(json.dumps(metadata))
        return self.websocket
    
    async def send(self):
        print("SENDING")
        while self.Run:
            if self.process.stdout is None:
                print("NO STDOUT")
                break
            data = await self.process.stdout.read(4096)
            await self.websocket.send(data)
        self.process.kill()
        await self.process.wait()
    
    async def recv(self,):
        try:
            while self.Run:
                # print("RECEIVING")
                frame = await self.websocket.recv()
                # print(len(frame))
                if frame == "DONE":
                    print("DONE")
                    await self.frames.put(False)
                    await self.audio.put(None)
                    return
                if isinstance(frame,bytes) and  frame.startswith(b"ChunkStart"):
                    print("CHUNK START" , int.from_bytes(frame[10:14], 'little'))
                    await self.frames.put(True)
                    continue
                # frame = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), flags=1)
                if frame is not None and isinstance(frame, bytes) and len(frame)>0:
                    # print("RECEIVED", len(frame))
                    try:
                        f = frame[9:9+int.from_bytes(frame[5:9], 'little')]
                        # f = np.frombuffer(f[12:], dtype=np.uint8)
                        # f = cv2.imdecode(f, flags=1)
                        await self.frames.put(f)
                        a = frame[18+int.from_bytes(frame[5:9], 'little'):]
                        await self.audio.put(a)
                    except Exception as e:
                        print(e)
        except websockets.exceptions.ConnectionClosed as e:
            print("DISCONNECTED", e)

        except Exception:
            import traceback
            traceback.print_exc()
            
        await self.frames.put(False)
    
    async def GetStreams(self):
        return self.videoTrack, self.audioTrack
    
    async def Exit(self):
        self.Run = False
        await self.websocket.send(b"DONE")
        await self.websocket.close()
        # await self.ReceiveTask
        await self.sendTask
