import argparse
import asyncio
from hmac import new
import json
import logging
import os
import ssl
import uuid

# import uvloop
import numpy as np
import cv2
from aiohttp import web
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from CustomMediaStreams import WSRadio, WebSocketReceiver, EchoTrack
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
import fractions

ROOT = os.path.dirname(__file__)
# uvloop.install()
logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
bh = MediaBlackhole()


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    # player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # saveFile = open("saveFile.pcm", "wb")
    metadata = {
        "video_reference_url": "https://storage.googleapis.com/charactervideos/11c30c18-86c3-424e-bb29-9c6d1fd6003b/11c30c18-86c3-424e-bb29-9c6d1fd6003b.mp4",
        "face_det_results": "https://storage.googleapis.com/charactervideos/11c30c18-86c3-424e-bb29-9c6d1fd6003b/11c30c18-86c3-424e-bb29-9c6d1fd6003b.pkl",
        "isSuperResolution": True,
        "isJPG": True,
        "syncAudio": True,
    }
    a = WSRadio()
    await a.Config(metadata)
    vt, at = await a.GetStreams()

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(
                at
            )

            bh.addTrack(track)

        elif track.kind == "video":
            pc.addTrack(
                vt
            )
            bh.addTrack(track)
            if args.record_to:
                recorder.addTrack(relay.subscribe(track))

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()
            await pc.close()
            await bh.stop()
            await a.Exit()

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()
    await bh.start()
    # send answer
    answer = await pc.createAnswer()
    if answer is None:
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": "Can't answer now"}),
        )

    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for HTTP server (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
