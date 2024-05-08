# Simli Radio Demo

This is a showcase of the [Simli Lipsync API](ws://api.simli.ai/LipsyncStream) in action. The demo works by getting an mp3 radio stream, converting it to pcm16 using ffmpeg and sending the pcm16 frames to the Simli Lipsync API over websockets. There are two available demos in this repository:

1. *OpenCVRenderer.py*: Uses OpenCV and PyAudio to render the video and audio on the screen.
2. *WebRTCRenderer/server.py*: Uses [aiortc](https://github.com/aiortc/aiortc) as a server to stream the video and audio to a web client using WebRTC.

## Installation

0. Use python 3.11, anything lower is not guaranteed to work *Fast enough*.
1. Install [FFMPEG](https://ffmpeg.org/download.html)
2. Create a virtual environment and install the requirements:

on Linux/MacOS

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

``` bash
pip install -r requirements.txt
```

## Usage

### OpenCVRenderer.py

``` bash
python OpenCVRenderer.py
```

To close just enter ctrl+c in the terminal.

### WebRTCRenderer/server.py

``` bash
python WebRTCRenderer/server.py
```

Then open [127.0.0.1:8080](127.0.0.1:8080) in your browser.
