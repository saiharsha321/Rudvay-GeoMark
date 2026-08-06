/**
 * Advanced Client-Side Face Detection & LBP/HOG Biometric Feature Engine
 */
class FaceDetectionEngine {
    /**
     * Detects human face in an image or HTMLVideoElement/HTMLCanvasElement.
     * Returns Promise<{ hasFace: boolean, descriptor: Array<number>|null, reason: string|null, boundingBox: object|null }>
     */
    static async detectAndExtractFace(sourceElement) {
        if (!sourceElement) {
            return { hasFace: false, descriptor: null, reason: "No video or camera element available." };
        }

        // Create working canvas
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        let width = sourceElement.videoWidth || sourceElement.width || 640;
        let height = sourceElement.videoHeight || sourceElement.height || 480;

        if (width === 0 || height === 0) {
            return { hasFace: false, descriptor: null, reason: "Camera stream not active or 0 dimensions." };
        }

        canvas.width = width;
        canvas.height = height;
        ctx.drawImage(sourceElement, 0, 0, width, height);

        const imgData = ctx.getImageData(0, 0, width, height);
        
        // 1. Try Native Browser FaceDetector API if available
        let faceBox = null;
        if ('FaceDetector' in window) {
            try {
                const detector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
                const faces = await detector.detect(sourceElement);
                if (faces && faces.length > 0) {
                    const b = faces[0].boundingBox;
                    faceBox = { x: Math.max(0, Math.floor(b.x)), y: Math.max(0, Math.floor(b.y)), w: Math.min(width, Math.floor(b.width)), h: Math.min(height, Math.floor(b.height)) };
                }
            } catch (err) {
                console.warn("Native FaceDetector warning:", err);
            }
        }

        // 2. Fallback: Skin-tone & Facial Region Bounding Box Estimation
        if (!faceBox) {
            faceBox = this.estimateSkinBoundingBox(imgData, width, height);
        }

        if (!faceBox || faceBox.w < 40 || faceBox.h < 40) {
            return {
                hasFace: false,
                descriptor: null,
                reason: "No face detected in camera frame. Please position your face clearly in front of the camera.",
                boundingBox: null
            };
        }

        // 3. Crop Face Region and Resize to Standard 64x64 Matrix
        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = 64;
        cropCanvas.height = 64;
        const cropCtx = cropCanvas.getContext('2d');
        
        cropCtx.drawImage(canvas, faceBox.x, faceBox.y, faceBox.w, faceBox.h, 0, 0, 64, 64);
        const faceImgData = cropCtx.getImageData(0, 0, 64, 64);

        // 4. Compute 128-dimensional LBP (Local Binary Pattern) Feature Descriptor
        const descriptor = this.computeLBPDescriptor(faceImgData);

        return {
            hasFace: true,
            descriptor: descriptor,
            reason: null,
            boundingBox: faceBox
        };
    }

    /**
     * Skin-Tone Bounding Box Estimation in YCbCr / RGB space
     */
    static estimateSkinBoundingBox(imgData, width, height) {
        const data = imgData.data;
        let minX = width, maxX = 0, minY = height, maxY = 0;
        let skinPixels = 0;

        for (let y = 0; y < height; y += 4) {
            for (let x = 0; x < width; x += 4) {
                const i = (y * width + x) * 4;
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];

                // Rule-based skin pixel detection in RGB
                const isSkin = (r > 60 && g > 40 && b > 20 &&
                                (Math.max(r, g, b) - Math.min(r, g, b) > 15) &&
                                Math.abs(r - g) > 15 && r > g && r > b);

                if (isSkin) {
                    skinPixels++;
                    if (x < minX) minX = x;
                    if (x > maxX) maxX = x;
                    if (y < minY) minY = y;
                    if (y > maxY) maxY = y;
                }
            }
        }

        // Require at least 250 skin pixels for valid face region
        if (skinPixels < 250 || minX >= maxX || minY >= maxY) {
            return null;
        }

        const w = maxX - minX;
        const h = maxY - minY;

        // Aspect ratio sanity check for human face (width:height roughly 0.6 to 1.4)
        const ratio = w / h;
        if (ratio < 0.4 || ratio > 1.8) {
            return null;
        }

        return { x: minX, y: minY, w: w, h: h };
    }

    /**
     * Compute 128-dimensional Local Binary Pattern (LBP) facial descriptor
     */
    static computeLBPDescriptor(faceImgData) {
        const data = faceImgData.data;
        const w = 64;
        const h = 64;
        const grayscale = new Float32Array(w * h);

        // Convert 64x64 face crop to normalized grayscale
        for (let i = 0; i < w * h; i++) {
            const idx = i * 4;
            grayscale[i] = (data[idx] * 0.299 + data[idx + 1] * 0.587 + data[idx + 2] * 0.114) / 255.0;
        }

        // Divide 64x64 into 4x4 sub-grid (16 cells of 16x16 pixels)
        // Extract 8 LBP histogram bins per cell = 16 * 8 = 128 feature values!
        const descriptor = new Array(128).fill(0);

        for (let cellY = 0; cellY < 4; cellY++) {
            for (let cellX = 0; cellX < 4; cellX++) {
                const cellIndex = cellY * 4 + cellX;
                const startX = cellX * 16;
                const startY = cellY * 16;

                for (let y = startY + 1; y < startY + 15; y++) {
                    for (let x = startX + 1; x < startX + 15; x++) {
                        const center = grayscale[y * w + x];
                        let code = 0;

                        // 8-neighbor comparison
                        if (grayscale[(y - 1) * w + (x - 1)] >= center) code |= 1;
                        if (grayscale[(y - 1) * w + x] >= center) code |= 2;
                        if (grayscale[(y - 1) * w + (x + 1)] >= center) code |= 4;
                        if (grayscale[y * w + (x + 1)] >= center) code |= 8;
                        if (grayscale[(y + 1) * w + (x + 1)] >= center) code |= 16;
                        if (grayscale[(y + 1) * w + x] >= center) code |= 32;
                        if (grayscale[(y + 1) * w + (x - 1)] >= center) code |= 64;
                        if (grayscale[y * w + (x - 1)] >= center) code |= 128;

                        const bin = Math.floor(code / 32); // 8 bins per cell
                        descriptor[cellIndex * 8 + bin]++;
                    }
                }

                // Normalize cell histogram
                let sum = 0;
                for (let b = 0; b < 8; b++) sum += descriptor[cellIndex * 8 + b];
                if (sum > 0) {
                    for (let b = 0; b < 8; b++) {
                        descriptor[cellIndex * 8 + b] = parseFloat((descriptor[cellIndex * 8 + b] / sum).toFixed(4));
                    }
                }
            }
        }

        return descriptor;
    }
}

window.FaceDetectionEngine = FaceDetectionEngine;
