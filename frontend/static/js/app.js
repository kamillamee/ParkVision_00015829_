/* Application utilities */

function showToast(message, type) {
    type = type || 'error';
    let el = document.getElementById('toast-el');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toast-el';
        el.className = 'toast ' + type;
        document.body.appendChild(el);
    }
    el.textContent = message;
    el.className = 'toast ' + type + ' visible';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
        el.classList.remove('visible');
    }, 4000);
}

function setButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.setAttribute('data-original-text', btn.textContent);
        btn.innerHTML = '<span class="loading-spinner" style="width:20px;height:20px;border-width:2px;display:inline-block;vertical-align:middle;"></span> Loading...';
    } else {
        btn.disabled = false;
        btn.textContent = btn.getAttribute('data-original-text') || 'Submit';
    }
}

function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '/login.html';
        return false;
    }
    api.token = token;
    return true;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login.html';
}

const PARKING_MAP_SIZE = { width: 2560, height: 1440 };
/** @type {Record<string, object>} */
const slotsConfigCache = {};

async function getSlotsConfig(lotId) {
    const key = lotId == null ? '1' : String(lotId);
    if (slotsConfigCache[key]) {
        return slotsConfigCache[key];
    }
    const lid = lotId == null ? 1 : lotId;
    slotsConfigCache[key] = await api.getSlotsConfig(lid);
    return slotsConfigCache[key];
}

function mediaUrlForLot(lotId) {
    return '/api/stream/mjpeg/' + lotId;
}

/**
 * Fetch the natural pixel dimensions of the live frame for a lot.
 * Falls back to the British School default (2560×1440) if the image
 * is unavailable, so the overlay still renders rather than crashing.
 */
async function getFrameDimensions(lotId) {
    try {
        var r = await fetch('/api/stream/frame/' + lotId + '/meta');
        if (r.ok) {
            var j = await r.json();
            if (j.width && j.height) {
                return { width: j.width, height: j.height };
            }
        }
    } catch (_) {}
    return new Promise(function (resolve) {
        var img = new Image();
        img.onload = function () {
            resolve({
                width: img.naturalWidth || PARKING_MAP_SIZE.width,
                height: img.naturalHeight || PARKING_MAP_SIZE.height
            });
        };
        img.onerror = function () {
            resolve({ width: PARKING_MAP_SIZE.width, height: PARKING_MAP_SIZE.height });
        };
        img.src = mediaUrlForLot(lotId) + '?t=' + Date.now();
    });
}

/** Resolved from API on the home page — do not assume Westminster is id 2. */
let landingLiveLotIds = { british: null, westminster: null };

/**
 * Discover British School + Westminster lot IDs from /api/lots (names), then load both maps.
 */
async function initLandingLiveParking() {
    const lots = await api.getLots();
    const lower = function (n) {
        return (n || '').toLowerCase();
    };
    const british = lots.find(function (l) {
        return lower(l.name).indexOf('british') !== -1;
    });
    const west = lots.find(function (l) {
        return lower(l.name).indexOf('westminster') !== -1;
    });
    landingLiveLotIds.british = british ? british.id : null;
    landingLiveLotIds.westminster = west ? west.id : null;

    const g1 = document.getElementById('parking-grid-1');
    const g2 = document.getElementById('parking-grid-2');
    if (british && g1) {
        g1.setAttribute('data-lot-id', String(british.id));
        await loadParkingStatus({
            containerId: 'parking-grid-1',
            lotId: british.id,
            updateStats: false,
            frameHint: 'British School camera'
        });
    } else if (g1) {
        g1.innerHTML =
            '<div class="loading">British School lot not found in database.</div>';
    }
    if (west && g2) {
        g2.setAttribute('data-lot-id', String(west.id));
        await loadParkingStatus({
            containerId: 'parking-grid-2',
            lotId: west.id,
            updateStats: false,
            frameHint: 'Westminster camera — run python run.py (embedded MJPEG + vision)'
        });
    } else if (g2) {
        g2.innerHTML =
            '<div class="loading">Westminster lot not found. Run the server and apply DB migrations.</div>';
    }
    await refreshParkingStats(null);
}

async function refreshLandingLiveMaps() {
    if (landingLiveLotIds.british) {
        await loadParkingStatus({
            containerId: 'parking-grid-1',
            lotId: landingLiveLotIds.british,
            updateStats: false,
            frameHint: 'British School camera'
        });
    }
    if (landingLiveLotIds.westminster) {
        await loadParkingStatus({
            containerId: 'parking-grid-2',
            lotId: landingLiveLotIds.westminster,
            updateStats: false,
            frameHint: 'Westminster camera — run python run.py (embedded MJPEG + vision)'
        });
    }
    await refreshParkingStats(null);
}

function attachLiveFrameFallback(containerId, hint) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var img = container.querySelector('.parking-map-frame-a');
    if (!img) return;
    // Only show the "no JPEG" message if the image has NEVER successfully loaded.
    // Once the feed is live, transient errors (e.g. stream reconnect)
    // are handled silently by the double-buffer retry logic.
    var hasLoadedOnce = false;
    img.addEventListener('load', function () { hasLoadedOnce = true; }, { once: true });
    img.addEventListener(
        'error',
        function () {
            if (hasLoadedOnce) return; // feed was live — ignore transient errors
            stopLiveFrameRefresh(containerId);
            var wrap = container.querySelector('.parking-map-frame-wrap');
            if (!wrap) return;
            var safe = String(
                hint ||
                    'Start the server with embedded vision (python run.py). Ensure this lot is is_live and the video file exists.'
            ).replace(/</g, '&lt;');
            wrap.innerHTML =
                '<div class="live-frame-missing">' +
                '<p><strong>No live JPEG yet.</strong></p>' +
                '<p class="live-frame-missing-hint">' +
                safe +
                '</p></div>';
        },
        { once: true }
    );
}

function getPolygonBounds(points) {
    const xs = points.map(p => p[0]);
    const ys = points.map(p => p[1]);
    return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys)
    };
}

function polygonCentroid(points) {
    let sx = 0;
    let sy = 0;
    const n = points.length;
    if (!n) return [0, 0];
    for (let i = 0; i < n; i++) {
        sx += points[i][0];
        sy += points[i][1];
    }
    return [sx / n, sy / n];
}

function polygonToSvgPoints(points) {
    return points.map(p => p[0] + ',' + p[1]).join(' ');
}

function escapeSvgText(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeHtmlAttr(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;');
}

function occupationSourceLabel(src) {
    if (src === 'sensor') return 'Sensor';
    if (src === 'fused') return 'Fused';
    return 'Vision';
}

/** Transparent 1×1 GIF — placeholder so the second buffer img has a valid src before the first swap. */
const LIVE_FRAME_PLACEHOLDER =
    'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

const LIVE_FRAME_MS = 125; // ~8 FPS for smoother live view without overloading browser decode
/** @type {Record<string, { aborted: boolean, timeoutId: any, imageLoading: boolean, activeLayer: string }>} */
const liveFrameControllers = {};

function stopLiveFrameRefresh(containerId) {
    if (containerId) {
        const s = liveFrameControllers[containerId];
        if (s) {
            s.aborted = true;
            s.imageLoading = false;
            s.activeLayer = 'a';
            if (s.timeoutId !== null) {
                clearTimeout(s.timeoutId);
            }
            delete liveFrameControllers[containerId];
        }
        return;
    }
    Object.keys(liveFrameControllers).forEach(function (id) {
        stopLiveFrameRefresh(id);
    });
}

/**
 * Double-buffered frames per parking-map container.
 */
function ensureLiveFrameRefresh(containerId, lotId) {
    if (liveFrameControllers[containerId]) return;
    var wrapProbe = document.getElementById(containerId);
    if (wrapProbe) {
        var w = wrapProbe.querySelector('.parking-map-mjpeg');
        if (w) return;
    }

    const mediaBase = mediaUrlForLot(lotId);
    const s = {
        aborted: false,
        timeoutId: null,
        imageLoading: false,
        activeLayer: 'a'
    };
    liveFrameControllers[containerId] = s;
    s.aborted = false;

    function scheduleNext(delay) {
        if (s.aborted) return;
        if (s.timeoutId !== null) {
            clearTimeout(s.timeoutId);
        }
        s.timeoutId = setTimeout(tick, delay);
    }

    function tick() {
        s.timeoutId = null;
        if (s.aborted) return;
        if (s.imageLoading) {
            // Avoid overlapping image fetch/decode cycles under slow networks/CPUs.
            scheduleNext(LIVE_FRAME_MS);
            return;
        }
        const container = document.getElementById(containerId);
        if (!container) {
            delete liveFrameControllers[containerId];
            return;
        }
        const wrap = container.querySelector('.parking-map-frame-wrap');
        if (!wrap) return;
        const a = wrap.querySelector('.parking-map-frame-a');
        const b = wrap.querySelector('.parking-map-frame-b');
        if (!a || !b) return;

        const hidden = s.activeLayer === 'a' ? b : a;
        const visible = s.activeLayer === 'a' ? a : b;
        const url = mediaBase + '?t=' + Date.now();

        function swapAndContinue() {
            if (s.aborted) return;
            visible.classList.remove('parking-map-frame-visible');
            hidden.classList.add('parking-map-frame-visible');
            s.activeLayer = s.activeLayer === 'a' ? 'b' : 'a';
            scheduleNext(LIVE_FRAME_MS);
        }

        s.imageLoading = true;
        hidden.onload = function () {
            hidden.onload = null;
            hidden.onerror = null;
            s.imageLoading = false;
            if (s.aborted) return;
            if (typeof hidden.decode === 'function') {
                hidden.decode().then(swapAndContinue).catch(swapAndContinue);
            } else {
                swapAndContinue();
            }
        };
        hidden.onerror = function () {
            hidden.onload = null;
            hidden.onerror = null;
            s.imageLoading = false;
            if (!s.aborted) scheduleNext(LIVE_FRAME_MS);
        };
        hidden.src = url;
    }

    scheduleNext(0);
}

function updateParkingMapOverlays(container, slots, config) {
    for (let i = 0; i < slots.length; i++) {
        const slot = slots[i];
        const polygon = config[slot.slot_number];
        if (!polygon || !polygon.length) continue;
        const groups = container.querySelectorAll('g.slot-polygon-group[data-slot]');
        let g = null;
        for (let j = 0; j < groups.length; j++) {
            if (groups[j].getAttribute('data-slot') === String(slot.slot_number)) {
                g = groups[j];
                break;
            }
        }
        if (!g) continue;
        const occupied = !!slot.is_occupied;
        const cls = occupied ? 'occupied' : 'available';
        const sl = occupationSourceLabel(slot.occupation_source || 'vision');
        g.classList.remove('occupied', 'available');
        g.classList.add(cls);
        const poly = g.querySelector('.slot-polygon-shape');
        if (poly) {
            poly.classList.remove('occupied', 'available');
            poly.classList.add(cls);
        }
        g.querySelectorAll('.slot-polygon-label, .slot-polygon-source').forEach(function (el) {
            el.classList.remove('occupied', 'available');
            el.classList.add(cls);
        });
        const titleEl = g.querySelector('title');
        if (titleEl) {
            titleEl.textContent =
                slot.slot_number + ' - ' + (occupied ? 'Occupied' : 'Available') + ' (' + sl + ')';
        }
    }
}

async function refreshParkingStats(lotId) {
    try {
        const stats =
            lotId != null ? await api.getSlotStats(lotId) : await api.getSlotStats();
        if (document.getElementById('total-slots')) {
            document.getElementById('total-slots').textContent = stats.total;
        }
        if (document.getElementById('available-slots')) {
            document.getElementById('available-slots').textContent = stats.available;
        }
        if (document.getElementById('occupied-slots')) {
            document.getElementById('occupied-slots').textContent = stats.occupied;
        }
        if (document.getElementById('occupancy-rate')) {
            document.getElementById('occupancy-rate').textContent = stats.occupancy_rate + '%';
        }
    } catch (e) {
        console.warn('Could not load stats:', e);
    }
}

function filterStreamSlotsForLot(streamSlots, lotId, config) {
    return streamSlots.filter(function (s) {
        if (s.lot_id != null && s.lot_id !== undefined) {
            return Number(s.lot_id) === Number(lotId);
        }
        return config && config[s.slot_number];
    });
}

function handleSlotStreamMessage(streamSlots) {
    const grids = document.querySelectorAll('.parking-grid[data-lot-id]');
    if (grids.length === 0) {
        const c = document.getElementById('parking-grid');
        const cfg = slotsConfigCache['1'];
        if (c && c.querySelector('.parking-map-svg') && cfg) {
            updateParkingMapOverlays(c, filterStreamSlotsForLot(streamSlots, 1, cfg), cfg);
            var statsSingle = null;
            if (window.location.pathname.indexOf('lot.html') !== -1 && c.getAttribute('data-lot-id')) {
                statsSingle = parseInt(c.getAttribute('data-lot-id'), 10);
            }
            refreshParkingStats(statsSingle);
            return;
        }
        loadParkingStatus({ containerId: 'parking-grid', lotId: 1 });
        return;
    }
    for (let i = 0; i < grids.length; i++) {
        const container = grids[i];
        const lid = parseInt(container.getAttribute('data-lot-id'), 10);
        const cfg = slotsConfigCache[String(lid)];
        if (!container.querySelector('.parking-map-svg') || !cfg) continue;
        const filtered = filterStreamSlotsForLot(streamSlots, lid, cfg);
        updateParkingMapOverlays(container, filtered, cfg);
    }
    var statsForStream = null;
    if (
        window.location.pathname.indexOf('lot.html') !== -1 ||
        window.location.pathname.indexOf('dashboard.html') !== -1 ||
        window.location.pathname === '/' ||
        window.location.pathname.indexOf('index.html') !== -1
    ) {
        var pg = document.getElementById('parking-grid');
        if (pg && pg.getAttribute('data-lot-id')) {
            statsForStream = parseInt(pg.getAttribute('data-lot-id'), 10);
        }
    }
    refreshParkingStats(statsForStream);
}

async function loadParkingStatus(options) {
    options = options || {};
    const containerId = options.containerId || 'parking-grid';
    const lotId = options.lotId != null ? options.lotId : 1;
    const updateStats = options.updateStats !== false;
    const statsLotId = options.statsLotId;
    const frameHint = options.frameHint;

    try {
        const [slots, config] = await Promise.all([
            api.getSlotsStatus(lotId),
            getSlotsConfig(lotId)
        ]);
        const container = document.getElementById(containerId);

        if (!container) return;

        const hasConfig = config && Object.keys(config).length > 0;
        container.classList.toggle('parking-map', hasConfig);

        if (hasConfig) {
            const expected = slots.filter(function (s) {
                return config[s.slot_number] && config[s.slot_number].length;
            }).length;
            const svg = container.querySelector('.parking-map-svg');
            const currentLotId = container.getAttribute('data-lot-id');
            const sameLotAsDom =
                currentLotId != null && String(lotId) === String(currentLotId);
            if (svg && expected > 0 && sameLotAsDom) {
                const actual = container.querySelectorAll('g.slot-polygon-group[data-slot]').length;
                if (expected === actual) {
                    updateParkingMapOverlays(container, slots, config);
                    if (updateStats) {
                        await refreshParkingStats(
                            statsLotId !== undefined ? statsLotId : null
                        );
                    }
                    return;
                }
            }
        }

        if (!hasConfig) {
            stopLiveFrameRefresh(containerId);
            container.style.backgroundImage = '';
            const sourceLabel = (src) => occupationSourceLabel(src);
            container.innerHTML = slots.map(slot => `
                <div class="slot-card ${slot.is_occupied ? 'occupied' : 'available'}" title="${slot.slot_number} - ${slot.zone || ''}">
                    <div class="slot-number">${slot.slot_number}</div>
                    <div class="slot-status">${slot.is_occupied ? 'Occupied' : 'Available'}</div>
                    ${slot.zone ? `<div class="slot-zone">${slot.zone}</div>` : ''}
                    ${slot.occupation_source ? `<span class="slot-source badge-source">${sourceLabel(slot.occupation_source)}</span>` : ''}
                </div>
            `).join('');
            return;
        }

        const streamSrc = mediaUrlForLot(lotId);
        const frameStackHtml =
            '<div class="parking-map-frame-wrap">' +
            '<img class="parking-map-frame parking-map-frame-a parking-map-frame-visible parking-map-mjpeg" src="' +
            streamSrc +
            '" alt="Live parking stream" decoding="async">' +
            '</div>';
        // Use actual frame dimensions so the SVG viewBox matches the video
        // resolution of this specific lot (e.g. Westminster is 1280×720, not 2560×1440).
        const frameDims = await getFrameDimensions(lotId);
        const w = frameDims.width;
        const h = frameDims.height;
        const polygonsSvg = slots.map(slot => {
            const polygon = config[slot.slot_number];
            if (!polygon || !polygon.length) {
                return '';
            }
            const bounds = getPolygonBounds(polygon);
            const [cx, cy] = polygonCentroid(polygon);
            const pointsAttr = polygonToSvgPoints(polygon);
            const cls = slot.is_occupied ? 'occupied' : 'available';
            const src = slot.occupation_source;
            const sourceLabel = occupationSourceLabel(src);
            const tip = escapeSvgText(
                `${slot.slot_number} - ${slot.is_occupied ? 'Occupied' : 'Available'} (${sourceLabel})`
            );
            const srcX = bounds.maxX - 12;
            const srcY = bounds.maxY - 10;
            const ds = escapeHtmlAttr(slot.slot_number);
            return `
                <g class="slot-polygon-group ${cls}" data-slot="${ds}">
                    <title>${tip}</title>
                    <polygon class="slot-polygon-shape ${cls}" points="${pointsAttr}" />
                    <text class="slot-polygon-label ${cls}" font-size="48" x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" text-anchor="middle" dominant-baseline="central">${escapeSvgText(slot.slot_number)}</text>
                    ${src ? `<text class="slot-polygon-source ${cls}" font-size="24" x="${srcX.toFixed(1)}" y="${srcY.toFixed(1)}" text-anchor="end" dominant-baseline="auto">${escapeSvgText(sourceLabel)}</text>` : ''}
                </g>
            `;
        }).join('');

        container.setAttribute('data-lot-id', String(lotId));
        stopLiveFrameRefresh(containerId);
        container.style.backgroundImage = '';
        const noSlotsBanner =
            slots.length === 0
                ? '<div class="loading" style="margin-bottom:8px;">No parking slots configured for this lot yet (showing live frame only).</div>'
                : '';

        container.innerHTML =
            noSlotsBanner +
            frameStackHtml +
            '<div class="parking-map-overlay">' +
            '<svg class="parking-map-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid slice" aria-hidden="true">' +
            polygonsSvg +
            '</svg></div>';

        ensureLiveFrameRefresh(containerId, lotId);
        if (frameHint) {
            attachLiveFrameFallback(containerId, frameHint);
        }
        if (updateStats) {
            await refreshParkingStats(statsLotId !== undefined ? statsLotId : null);
        }
    } catch (error) {
        console.error('Error loading parking status:', error);
        const container = document.getElementById(containerId);
        if (container) {
            stopLiveFrameRefresh(containerId);
            const errorMsg = error.message || 'Error loading parking status';
            container.innerHTML = `<div class="loading" style="color: var(--danger);">${errorMsg}</div>`;
        }
    }
}

function connectSlotStream(onUpdate) {
    if (typeof EventSource === 'undefined') return null;
    var handle = { closed: false, es: null };
    var retryDelay = 2000;
    function connect() {
        if (handle.closed) return;
        try {
            var es = new EventSource('/api/slots/stream');
            handle.es = es;
            es.onmessage = function (e) {
                retryDelay = 2000; // reset backoff on success
                try {
                    var data = JSON.parse(e.data);
                    if (Array.isArray(data) && typeof onUpdate === 'function') onUpdate(data);
                } catch (_) {}
            };
            es.onerror = function () {
                es.close();
                handle.es = null;
                if (!handle.closed) {
                    setTimeout(connect, retryDelay);
                    retryDelay = Math.min(retryDelay * 2, 30000); // exponential backoff up to 30s
                }
            };
        } catch (e) {
            if (!handle.closed) {
                setTimeout(connect, retryDelay);
                retryDelay = Math.min(retryDelay * 2, 30000);
            }
        }
    }
    connect();
    return handle; // always truthy so caller knows SSE is active
}
