# Simli Radio Demo

This is a showcase of the [Simli Lipsync API](ws://api.simli.ai/LipsyncStream) in action. The demo works by getting an mp3 radio stream, converting it to pcm16 using ffmpeg and sending the pcm16 frames to the Simli Lipsync API over websockets.

1. *OpenCVRenderer.py*: Uses OpenCV and PyAudio to render the video and audio on the screen.

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

! Disclaimer: Moving the OpenCV window around can cause the audio to be out of sync with the video.

``` bash
python OpenCVRenderer.py
```

To close just enter ctrl+c in the terminal.
