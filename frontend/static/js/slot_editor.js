// Use lot-aware latest frame (default lot_id=1) or place.png as fallback.
// Supports:
//   ?lot_id=NUM
//   ?lot=westminster|british  (resolved via /api/lots)
const query = new URLSearchParams(window.location.search);
let lotId = Number(query.get('lot_id') || '1');
const lotKey = (query.get('lot') || '').trim().toLowerCase();
let IMAGE_URL = '/media/lot/' + lotId + '/latest.jpg';
const IMAGE_FALLBACK = '/media/place.png';

const canvas = document.getElementById('editor-canvas');
const ctx = canvas.getContext('2d');
const currentPointsEl = document.getElementById('current-points');
const slotsJsonEl = document.getElementById('slots-json');
const slotNameEl = document.getElementById('slot-name');
const saveSlotBtn = document.getElementById('save-slot');
const undoPointBtn = document.getElementById('undo-point');
const clearCurrentBtn = document.getElementById('clear-current');
const clearAllBtn = document.getElementById('clear-all');
const copyJsonBtn = document.getElementById('copy-json');
const downloadJsonBtn = document.getElementById('download-json');
const loadExistingBtn = document.getElementById('load-existing');

let image = new Image();
let currentPoints = [];
let slots = {};

function drawCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0);

    // Draw saved slots
    Object.entries(slots).forEach(([slot, points]) => {
        drawPolygon(points, 'rgba(16, 185, 129, 0.4)', '#059669');
        drawLabel(points, slot, '#065f46');
    });

    // Draw current slot
    if (currentPoints.length > 0) {
        drawPolygon(currentPoints, 'rgba(59, 130, 246, 0.3)', '#2563eb');
        drawPoints(currentPoints, '#2563eb');
    }
}

function drawPolygon(points, fill, stroke) {
    if (points.length === 0) return;
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
    if (points.length >= 3) ctx.closePath();
    ctx.fillStyle = fill;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.fill();
    ctx.stroke();
}

function drawPoints(points, color) {
    ctx.fillStyle = color;
    points.forEach(p => {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 4, 0, Math.PI * 2);
        ctx.fill();
    });
}

function drawLabel(points, label, color) {
    const x = points.reduce((sum, p) => sum + p[0], 0) / points.length;
    const y = points.reduce((sum, p) => sum + p[1], 0) / points.length;
    ctx.fillStyle = color;
    ctx.font = '14px sans-serif';
    ctx.fillText(label, x - 8, y + 4);
}

function updateUI() {
    currentPointsEl.textContent = JSON.stringify(currentPoints, null, 2);
    slotsJsonEl.value = JSON.stringify(slots, null, 2);
    saveSlotBtn.disabled = currentPoints.length !== 4 || !slotNameEl.value.trim();
}

function canvasPointFromEvent(event) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);
    return [x, y];
}

canvas.addEventListener('click', (event) => {
    if (currentPoints.length >= 4) return;
    currentPoints.push(canvasPointFromEvent(event));
    updateUI();
    drawCanvas();
});

saveSlotBtn.addEventListener('click', () => {
    const name = slotNameEl.value.trim();
    if (!name || currentPoints.length !== 4) return;
    slots[name] = currentPoints.slice();
    currentPoints = [];
    slotNameEl.value = '';
    updateUI();
    drawCanvas();
});

undoPointBtn.addEventListener('click', () => {
    currentPoints.pop();
    updateUI();
    drawCanvas();
});

clearCurrentBtn.addEventListener('click', () => {
    currentPoints = [];
    updateUI();
    drawCanvas();
});

clearAllBtn.addEventListener('click', () => {
    slots = {};
    updateUI();
    drawCanvas();
});

copyJsonBtn.addEventListener('click', async () => {
    await navigator.clipboard.writeText(slotsJsonEl.value);
});

downloadJsonBtn.addEventListener('click', () => {
    const blob = new Blob([slotsJsonEl.value], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = lotId === 2 ? 'slots-west.json' : 'slots.json';
    a.click();
    URL.revokeObjectURL(url);
});

loadExistingBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/slots/config?lot_id=' + lotId);
        if (res.ok) {
            slots = await res.json();
            updateUI();
            drawCanvas();
        }
    } catch (e) {
        // ignore
    }
});

image.onload = () => {
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    updateUI();
    drawCanvas();
};

image.onerror = () => {
    if (image.src.indexOf('latest.jpg') >= 0) {
        image.src = IMAGE_FALLBACK;
    }
};

async function resolveLotIdFromName() {
    if (!lotKey) return;
    try {
        const res = await fetch('/api/lots');
        if (!res.ok) return;
        const lots = await res.json();
        if (!Array.isArray(lots)) return;

        const match = lots.find(l => {
            const n = String((l && l.name) || '').toLowerCase();
            if (lotKey === 'westminster') return n.indexOf('westminster') !== -1;
            if (lotKey === 'british') return n.indexOf('british') !== -1;
            return n.indexOf(lotKey) !== -1;
        });
        if (match && match.id != null) {
            lotId = Number(match.id);
            IMAGE_URL = '/media/lot/' + lotId + '/latest.jpg';
        }
    } catch (e) {
        // keep defaults if lookup fails
    }
}

async function initEditor() {
    await resolveLotIdFromName();
    image.src = IMAGE_URL;
}

initEditor();
