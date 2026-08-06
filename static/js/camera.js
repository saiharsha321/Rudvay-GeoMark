/**
 * WebRTC Camera Stream & Photo Snapshot Module
 */
class CameraManager {
    constructor(videoElementId, canvasElementId) {
        this.videoElement = document.getElementById(videoElementId);
        this.canvasElement = document.getElementById(canvasElementId);
        this.stream = null;
        this.capturedImageB64 = null;
    }

    async startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            console.warn("getUserMedia is not supported or blocked in this browser context (HTTP IP).");
            this.showFallbackUI();
            return false;
        }

        try {
            const constraints = {
                video: {
                    facingMode: 'user',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                },
                audio: false
            };

            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            if (this.videoElement) {
                this.videoElement.srcObject = this.stream;
                this.videoElement.onloadedmetadata = () => {
                    this.videoElement.play().catch(e => console.warn("Auto-play prevented:", e));
                };
            }
            return true;
        } catch (err) {
            console.error("Camera access error:", err);
            this.showFallbackUI();
            return false;
        }
    }

    showFallbackUI() {
        const fallbackBox = document.getElementById('camera-fallback-box');
        if (fallbackBox) {
            fallbackBox.classList.remove('hidden');
        }
    }

    setCapturedBase64(b64) {
        this.capturedImageB64 = b64;
    }

    captureSnapshot() {
        if (this.capturedImageB64) {
            return this.capturedImageB64;
        }

        if (!this.videoElement || !this.canvasElement) return null;
        
        const context = this.canvasElement.getContext('2d');
        const width = this.videoElement.videoWidth || 640;
        const height = this.videoElement.videoHeight || 480;

        if (width === 0 || height === 0) {
            console.warn("Video dimensions 0, returning null snapshot");
            return null;
        }

        this.canvasElement.width = width;
        this.canvasElement.height = height;

        context.drawImage(this.videoElement, 0, 0, width, height);
        
        return this.canvasElement.toDataURL('image/jpeg', 0.85);
    }

    async captureFaceDescriptor() {
        const source = (this.videoElement && this.videoElement.videoWidth > 0) ? this.videoElement : this.canvasElement;
        if (!source) {
            return { hasFace: false, descriptor: null, reason: "No active video or canvas source available." };
        }

        if (window.FaceDetectionEngine) {
            return await window.FaceDetectionEngine.detectAndExtractFace(source);
        }
        return { hasFace: false, descriptor: null, reason: "Face Detection Engine script not loaded." };
    }

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
    }
}
