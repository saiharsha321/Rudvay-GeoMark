/**
 * Leaflet.js Interactive Geofence Map Configurator
 */
function initGeofenceMap(mapElementId, initialLat, initialLng, initialRadius, latInputId, lngInputId, radiusSliderId, radiusDisplayId) {
    const latInput = document.getElementById(latInputId);
    const lngInput = document.getElementById(lngInputId);
    const radiusSlider = document.getElementById(radiusSliderId);
    const radiusDisplay = document.getElementById(radiusDisplayId);

    const lat = parseFloat(initialLat) || 17.385044;
    const lng = parseFloat(initialLng) || 78.486671;
    const radius = parseFloat(initialRadius) || 200;

    // Initialize Leaflet map
    const map = L.map(mapElementId).setView([lat, lng], 16);

    // OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Draggable marker
    const marker = L.marker([lat, lng], { draggable: true }).addTo(map);

    // Geofence circle overlay
    const circle = L.circle([lat, lng], {
        color: '#4F46E5',
        fillColor: '#818CF8',
        fillOpacity: 0.3,
        radius: radius
    }).addTo(map);

    function updateInputs(newLat, newLng) {
        if (latInput) latInput.value = newLat.toFixed(6);
        if (lngInput) lngInput.value = newLng.toFixed(6);
    }

    function updateCircle() {
        const curPos = marker.getLatLng();
        const r = parseFloat(radiusSlider ? radiusSlider.value : radius);
        circle.setLatLng(curPos);
        circle.setRadius(r);
        if (radiusDisplay) radiusDisplay.innerText = r + 'm';
    }

    // Marker drag event listener
    marker.on('dragend', function (e) {
        const pos = e.target.getLatLng();
        updateInputs(pos.lat, pos.lng);
        updateCircle();
    });

    // Map click listener to relocate pin
    map.on('click', function (e) {
        marker.setLatLng(e.latlng);
        updateInputs(e.latlng.lat, e.latlng.lng);
        updateCircle();
    });

    // Slider change listener
    if (radiusSlider) {
        radiusSlider.addEventListener('input', updateCircle);
    }

    // Input blur listener
    if (latInput && lngInput) {
        const updateFromInputs = () => {
            const l = parseFloat(latInput.value);
            const lg = parseFloat(lngInput.value);
            if (!isNaN(l) && !isNaN(lg)) {
                const newPos = L.latLng(l, lg);
                marker.setLatLng(newPos);
                map.panTo(newPos);
                updateCircle();
            }
        };
        latInput.addEventListener('change', updateFromInputs);
        lngInput.addEventListener('change', updateFromInputs);
    }

    // Handlers for "Use My Location"
    const useLocationBtn = document.getElementById('btn-use-current-location');
    if (useLocationBtn) {
        useLocationBtn.addEventListener('click', () => {
            if (!navigator.geolocation) {
                alert("Geolocation is not supported by your browser.");
                return;
            }
            useLocationBtn.disabled = true;
            useLocationBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Locating...';

            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const cLat = pos.coords.latitude;
                    const cLng = pos.coords.longitude;
                    const newPos = L.latLng(cLat, cLng);
                    marker.setLatLng(newPos);
                    map.setView(newPos, 16);
                    updateInputs(cLat, cLng);
                    updateCircle();
                    useLocationBtn.disabled = false;
                    useLocationBtn.innerHTML = '<i class="fas fa-crosshairs mr-1"></i> Use My Location';
                },
                (err) => {
                    console.error("Location error:", err);
                    alert("Unable to retrieve location: " + err.message);
                    useLocationBtn.disabled = false;
                    useLocationBtn.innerHTML = '<i class="fas fa-crosshairs mr-1"></i> Use My Location';
                },
                { enableHighAccuracy: true, timeout: 8000 }
            );
        });
    }

    // Handlers for Nominatim Map Place Search
    const searchBtn = document.getElementById('btn-search-location');
    const searchInput = document.getElementById('map-search-input');
    const addressInput = document.getElementById('address-input');

    if (searchBtn && searchInput) {
        const performSearch = async () => {
            const query = searchInput.value.trim();
            if (!query) return;

            searchBtn.disabled = true;
            searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            try {
                const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`);
                const results = await res.json();

                if (results && results.length > 0) {
                    const top = results[0];
                    const sLat = parseFloat(top.lat);
                    const sLng = parseFloat(top.lon);
                    const newPos = L.latLng(sLat, sLng);

                    marker.setLatLng(newPos);
                    map.setView(newPos, 16);
                    updateInputs(sLat, sLng);
                    updateCircle();

                    if (addressInput && (!addressInput.value || addressInput.value.startsWith('Lat:'))) {
                        addressInput.value = top.display_name.split(',')[0] + ', ' + (top.display_name.split(',')[1] || '');
                    }
                } else {
                    alert("Location not found. Please try a more specific landmark or address.");
                }
            } catch (err) {
                console.error("Search error:", err);
                alert("Search service error. Please try again.");
            } finally {
                searchBtn.disabled = false;
                searchBtn.innerHTML = 'Search';
            }
        };

        searchBtn.addEventListener('click', performSearch);
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                performSearch();
            }
        });
    }

    return { map, marker, circle };
}
