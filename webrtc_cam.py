import asyncio
import cv2
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaStreamTrack
import json
from aiohttp_cors import setup as setup_cors, ResourceOptions

# Store active WebRTC connections
pcs = set()

class VideoStreamTrack(MediaStreamTrack):
    """ WebRTC Video StreamTrack from USB webcam on Raspberry Pi """
    kind = "video"

    def __init__(self):
        super().__init__()

        # ✅ Use `/dev/video0` for Raspberry Pi's USB webcam
        self.cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Set width
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Set height

        if not self.cap.isOpened():
            raise RuntimeError("❌ Failed to open the USB webcam. Try using /dev/video1")

    async def recv(self):
        """Capture frames and send via WebRTC"""
        success, frame = self.cap.read()
        if not success:
            print("⚠️ No frame received from the camera")
            return None

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.ascontiguousarray(frame)
        return frame

async def offer(request):
    """Handle WebRTC offer from the terminal."""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # ✅ Ensure that at least one media track is added
    video_track = VideoStreamTrack()
    if video_track:
        pc.addTrack(video_track)  # Attach camera feed
    else:
        return web.json_response({"error": "No valid media track found"}, status=400)

    await pc.setRemoteDescription(offer)
    
    # ✅ Ensure offer direction is valid before creating an answer
    if not pc.getTransceivers():
        return web.json_response({"error": "No media transceivers available"}, status=400)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)  # ✅ Ensured track is added before calling

    return web.json_response({
        'sdp': pc.localDescription.sdp,
        'type': pc.localDescription.type
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })

async def cleanup():
    """Close all WebRTC peer connections on exit."""
    for pc in pcs:
        await pc.close()
    pcs.clear()

app = web.Application()
app.add_routes([web.post("/offer", offer)])

# ✅ Enable CORS for all routes
cors = setup_cors(app, defaults={
    "*": ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
for route in list(app.router.routes()):
    cors.add(route)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8083)
