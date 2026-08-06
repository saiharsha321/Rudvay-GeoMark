/**
 * Employee Mobile Punch & Geolocation Logic
 */
let cameraManager = null;
let currentCoords = null;
let tenantGeofence = null;
let verificationRequirements = null;

// Haversine formula in JavaScript for instant UI feedback
function calculateHaversineJS(lat1, lon1, lat2, lon2) {
    const R = 6371000.0; // meters
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.round(R * c);
}

document.addEventListener('DOMContentLoaded', () => {
    const verifyForm = document.getElementById('verify-form');
    const punchSection = document.getElementById('punch-section');
    const verifySection = document.getElementById('verify-section');
    const empNameDisplay = document.getElementById('emp-name-display');
    const tenantNameDisplay = document.getElementById('tenant-name-display');
    const geoBadge = document.getElementById('geo-status-badge');
    const btnPunchIn = document.getElementById('btn-punch-in');
    const btnPunchOut = document.getElementById('btn-punch-out');
    const resultModal = document.getElementById('result-modal');
    const resultTitle = document.getElementById('result-title');
    const resultBody = document.getElementById('result-body');
    const resultPhoto = document.getElementById('result-photo');
    const closeResultBtn = document.getElementById('btn-close-result');
    const httpWarning = document.getElementById('http-warning-banner');
    const manualGpsModal = document.getElementById('manual-gps-modal');
    const btnSetTestGps = document.getElementById('btn-set-test-gps');

    // Live Indian Standard Time (IST, UTC+05:30) Clock Ticker
    function updateISTClock() {
        const clockElem = document.getElementById('ist-live-clock');
        if (!clockElem) return;
        const now = new Date();
        const optionsDate = { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric' };
        const optionsTime = { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
        const dateStr = now.toLocaleDateString('en-IN', optionsDate);
        const timeStr = now.toLocaleTimeString('en-IN', optionsTime);
        clockElem.innerText = `${timeStr} IST • ${dateStr}`;
    }
    setInterval(updateISTClock, 1000);
    updateISTClock();

    // Check if running in Insecure Context (HTTP over non-localhost IP like 192.168.x.x)
    const isSecure = window.isSecureContext || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (!isSecure && httpWarning) {
        httpWarning.classList.remove('hidden');
    }

    // Handle Employee Verification Form Submission
    if (verifyForm) {
        verifyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const identifier = document.getElementById('identifier-input').value.trim();
            if (!identifier) return;

            const btn = document.getElementById('btn-verify');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Verifying...';

            try {
                const formData = new FormData();
                formData.append('identifier', identifier);

                const response = await fetch('/punch/verify', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    tenantGeofence = data.geofence;
                    verificationRequirements = data.verification_requirements;
                    empNameDisplay.innerText = data.employee.full_name + ' (' + data.employee.unique_emp_code + ')';
                    tenantNameDisplay.innerText = data.tenant_name;

                    verifySection.classList.add('hidden');
                    punchSection.classList.remove('hidden');

                    // Toggle PIN input if required
                    const pinBox = document.getElementById('pin-input-container');
                    if (pinBox) {
                        if (data.verification_requirements && data.verification_requirements.require_pin) {
                            pinBox.classList.remove('hidden');
                        } else {
                            pinBox.classList.add('hidden');
                        }
                    }

                    // Start camera
                    cameraManager = new CameraManager('webcam-video', 'webcam-canvas');
                    const cameraStarted = await cameraManager.startCamera();
                    
                    // Attach fallback file camera picker listener
                    const fileInput = document.getElementById('file-photo-input');
                    const previewImg = document.getElementById('photo-preview-img');
                    const videoElem = document.getElementById('webcam-video');

                    if (fileInput) {
                        fileInput.addEventListener('change', (e) => {
                            const file = e.target.files[0];
                            if (file) {
                                const reader = new FileReader();
                                reader.onload = (evt) => {
                                    const b64 = evt.target.result;
                                    cameraManager.setCapturedBase64(b64);
                                    if (previewImg) {
                                        previewImg.src = b64;
                                        previewImg.classList.remove('hidden');
                                    }
                                    if (videoElem) {
                                        videoElem.classList.add('hidden');
                                    }
                                };
                                reader.readAsDataURL(file);
                            }
                        });
                    }

                    // Acquire GPS coordinates
                    fetchLocation();
                } else {
                    alert(data.message || 'Verification failed.');
                }
            } catch (err) {
                console.error("Verification error:", err);
                alert("Server connection error. Please try again.");
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-arrow-right mr-2"></i> Continue to Punch';
            }
        });
    }

    // Acquire Geolocation with 10-Meter Precision
    function fetchLocation() {
        if (!navigator.geolocation) {
            handleGpsFailure('GPS Hardware Unsupported in Browser');
            return;
        }

        geoBadge.innerText = 'Acquiring High-Precision GPS...';

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const acc = Math.round(pos.coords.accuracy * 10) / 10;
                updatePosition(pos.coords.latitude, pos.coords.longitude, acc);
            },
            (err) => {
                console.error("GPS Error:", err);
                let errReason = "Location permission denied";
                if (err.code === 1) errReason = "GPS Permission Denied by User/Browser";
                else if (err.code === 2) errReason = "Position Unavailable";
                else if (err.code === 3) errReason = "GPS Request Timed Out";
                
                handleGpsFailure(errReason);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    function updatePosition(lat, lng, accuracyMeters = 0.0) {
        currentCoords = { latitude: lat, longitude: lng, accuracy: accuracyMeters };

        if (tenantGeofence && tenantGeofence.latitude) {
            const dist = calculateHaversineJS(
                currentCoords.latitude,
                currentCoords.longitude,
                parseFloat(tenantGeofence.latitude),
                parseFloat(tenantGeofence.longitude)
            );
            const maxRadius = parseFloat(tenantGeofence.radius_meters || 10.0);
            const accStr = accuracyMeters > 0 ? ` | ±${accuracyMeters}m` : '';

            if (accuracyMeters > 25.0) {
                geoBadge.className = 'px-3 py-1.5 text-xs font-semibold rounded-full bg-amber-500 text-white border border-amber-400 shadow-sm flex items-center gap-1.5 cursor-pointer';
                geoBadge.innerHTML = `<i class="fas fa-satellite text-sm animate-spin"></i> GPS Accuracy ±${accuracyMeters}m (Move outdoors for 10m precision)`;
            } else if (dist <= maxRadius) {
                geoBadge.className = 'px-3 py-1.5 text-xs font-semibold rounded-full bg-emerald-500 text-white border border-emerald-400 shadow-sm flex items-center gap-1.5';
                geoBadge.innerHTML = `<i class="fas fa-check-circle"></i> Inside Geofence (${dist}m${accStr})`;
            } else {
                geoBadge.className = 'px-3 py-1.5 text-xs font-semibold rounded-full bg-rose-500 text-white border border-rose-400 shadow-sm flex items-center gap-1.5 animate-pulse';
                geoBadge.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Outside Geofence (${dist}m / limit ${maxRadius}m${accStr})`;
            }
        }
    }

    function handleGpsFailure(reason) {
        geoBadge.className = 'px-3 py-1.5 text-xs font-semibold rounded-full bg-amber-500 text-white border border-amber-400 cursor-pointer shadow-sm flex items-center gap-1.5';
        geoBadge.innerHTML = `<i class="fas fa-triangle-exclamation"></i> GPS Blocked (Click to set location)`;
    }

    // Allow user to click badge to manually configure test GPS coordinates
    geoBadge.addEventListener('click', () => {
        if (manualGpsModal) {
            manualGpsModal.classList.remove('hidden');
        }
    });

    if (btnSetTestGps) {
        btnSetTestGps.addEventListener('click', () => {
            const tLat = parseFloat(document.getElementById('test-lat-input').value);
            const tLng = parseFloat(document.getElementById('test-lng-input').value);
            if (!isNaN(tLat) && !isNaN(tLng)) {
                updatePosition(tLat, tLng);
                manualGpsModal.classList.add('hidden');
            } else {
                alert("Please enter valid latitude and longitude numbers.");
            }
        });
    }

    const btnUseOfficeCenter = document.getElementById('btn-use-office-center');
    if (btnUseOfficeCenter) {
        btnUseOfficeCenter.addEventListener('click', () => {
            if (tenantGeofence && tenantGeofence.latitude && tenantGeofence.longitude) {
                const fLat = parseFloat(tenantGeofence.latitude);
                const fLng = parseFloat(tenantGeofence.longitude);
                document.getElementById('test-lat-input').value = fLat;
                document.getElementById('test-lng-input').value = fLng;
                updatePosition(fLat, fLng);
                manualGpsModal.classList.add('hidden');
            } else {
                alert("No workplace geofence location has been configured by your employer yet.");
            }
        });
    }

    // Submit Punch Handler
    async function submitPunch(type) {
        if (!currentCoords) {
            if (manualGpsModal) {
                manualGpsModal.classList.remove('hidden');
            } else {
                alert("GPS Location not set. Please grant permission or set test coordinates.");
            }
            return;
        }

        const photoB64 = cameraManager ? cameraManager.captureSnapshot() : '';
        let faceDescJson = '';
        
        if (cameraManager) {
            const faceRes = await cameraManager.captureFaceDescriptor();
            if (faceRes) {
                if (!faceRes.hasFace && verificationRequirements && (verificationRequirements.require_face || verificationRequirements.has_enrolled_face)) {
                    alert(faceRes.reason || "No face detected in camera frame. Please position your face clearly in front of the camera.");
                    return;
                }
                if (faceRes.descriptor) {
                    faceDescJson = JSON.stringify(faceRes.descriptor);
                }
            }
        }

        const pinVal = document.getElementById('pin-input') ? document.getElementById('pin-input').value.trim() : '';

        const btn = type === 'in' ? btnPunchIn : btnPunchOut;
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Submitting...';

        try {
            const formData = new FormData();
            formData.append('punch_type', type);
            formData.append('latitude', currentCoords.latitude);
            formData.append('longitude', currentCoords.longitude);
            formData.append('photo_base64', photoB64 || '');
            formData.append('face_descriptor', faceDescJson);
            formData.append('pin', pinVal || '');

            const response = await fetch('/punch/submit', {
                method: 'POST',
                body: formData
            });

            let data = {};
            try {
                data = await response.json();
            } catch (jsonErr) {
                data = { success: false, message: `Server error (${response.status}). Please try again.` };
            }

            if (data.success) {
                resultTitle.innerText = `Punch-${type.toUpperCase()} Successful!`;
                resultTitle.className = 'text-emerald-600 font-bold text-lg';
                
                resultBody.innerHTML = `
                    <div class="space-y-2 text-sm text-slate-700">
                        <p><strong>Status:</strong> <span class="font-semibold px-2 py-0.5 rounded ${data.status === 'ON_TIME' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${data.status}</span></p>
                        <p><strong>Time:</strong> ${data.punch_time}</p>
                        <p><strong>Distance to Fence:</strong> ${data.distance_meters} meters (Max allowed: ${data.radius_meters}m)</p>
                        <p class="text-xs text-slate-500">${data.message}</p>
                    </div>
                `;

                if (data.photo_url) {
                    resultPhoto.src = data.photo_url;
                    resultPhoto.classList.remove('hidden');
                } else {
                    resultPhoto.classList.add('hidden');
                }

                resultModal.classList.remove('hidden');
            } else {
                resultTitle.innerText = response.status === 401 ? "Session Expired" : "Attendance Submission Issue";
                resultTitle.className = 'text-rose-600 font-bold text-lg';
                
                resultBody.innerHTML = `
                    <div class="space-y-2 text-sm text-slate-700">
                        <p class="text-rose-600 font-bold"><i class="fas fa-exclamation-triangle mr-1"></i> ${response.status === 401 ? 'Verification Required' : 'Punch Error'}</p>
                        <p class="text-xs font-semibold text-rose-700 bg-rose-50 p-3 rounded-xl border border-rose-200">${data.message || "Punch submission failed."}</p>
                        ${data.distance_meters !== undefined ? `<p class="text-xs text-slate-500"><strong>Distance:</strong> ${data.distance_meters}m | <strong>Allowed Radius:</strong> ${data.radius_meters}m</p>` : ''}
                    </div>
                `;
                resultPhoto.classList.add('hidden');
                resultModal.classList.remove('hidden');
            }
        } catch (err) {
            console.error("Submission error:", err);
            resultTitle.innerText = "Connection Error";
            resultTitle.className = 'text-rose-600 font-bold text-lg';
            resultBody.innerHTML = `
                <div class="space-y-2 text-sm text-slate-700">
                    <p class="text-xs font-semibold text-rose-700 bg-rose-50 p-3 rounded-xl border border-rose-200">Unable to reach the server. Please check your network connection and try again.</p>
                </div>
            `;
            resultPhoto.classList.add('hidden');
            resultModal.classList.remove('hidden');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }

    if (btnPunchIn) btnPunchIn.addEventListener('click', () => submitPunch('in'));
    if (btnPunchOut) btnPunchOut.addEventListener('click', () => submitPunch('out'));
    if (closeResultBtn) {
        closeResultBtn.addEventListener('click', () => {
            resultModal.classList.add('hidden');
        });
    }
});
