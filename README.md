Smart Vision System

An AI-powered parking management platform that uses computer vision to detect real-time slot occupancy, lets users reserve spots, and gives admins full oversight of the system.

- What It Is

Smart Vision combines a **YOLO-based AI module** that analyzes live video feeds with a **FastAPI backend** and a **responsive web interface**. Occupancy is determined purely by computer vision (polygon IoU against YOLO vehicle detections) — no physical sensors are required. Users can see which spots are free, book a space in advance, and manage their vehicles — all in one place.

- How It Works

1. The AI module (`YOLO + OpenCV`) processes parking lot video and detects occupied/free slots.
2. Detected occupancy is sent to the backend via a protected internal endpoint (`X-API-Key`).
3. The backend stores slot state in SQLite and serves it through REST APIs.
4. The frontend shows live availability and lets users create/manage reservations.
5. Admins can view analytics, manage users, and read audit logs.



- Features

  User
- Phone-based registration and JWT authentication
- Real-time parking availability (color-coded slot grid)
- Interactive map with all parking lots
- Reserve a slot with date/time validation
- Manage multiple registered vehicles
- Save payment methods and confirm reservation payments
- Cancel reservations
- Parking assistant chat (OpenAI-backed or FAQ fallback)

  AI / Detection
- YOLOv11m vehicle detection on video frames
- Polygon-based slot occupancy using Shapely (area-overlap ratio + best-slot assignment per car)
- Optional Region-of-Interest mask and minimum bbox area filter to reject background cars
- Optional ByteTrack tracking (`--use-track`) for stable per-car identities
- Temporal smoothing with configurable acquire / release thresholds
- Supports multiple parking lots simultaneously
- Streams frames over MJPEG for live display in the browser

  Admin
- Dashboard statistics (users, reservations, slots)
- Reservations-by-day and top-slots analytics
- Enable/disable user accounts
- Full audit log

-

- Tech Stack

  Layer   Technology   Role  
 ----- ------- ---- 
  Backend   FastAPI + Uvicorn   REST API and static file serving  
  Database   SQLite + aiosqlite   Async persistent storage  
  Auth   python-jose + passlib/bcrypt   JWT tokens and password hashing  
  Validation   Pydantic v2   Request/response schemas  
  Rate limiting   slowapi   Protect auth and chat endpoints  
  AI detection   Ultralytics YOLO (v11m)   Vehicle detection  
  Video processing   OpenCV   Frame capture and JPEG export  
  Geometry   Shapely   Slot polygon overlap calculation  
  ML runtime   PyTorch   YOLO model inference  
  Frontend   HTML5 + CSS3 + Vanilla JS   No framework, fully responsive  
  Icons   Font Awesome 6   UI icons  
  Chat (optional)   OpenAI API   Parking assistant  

-

- Project Structure

 
SmartVision/
├── backend/
│   ├── app.py              # FastAPI app, startup, route registration
│   ├── database.py         # Schema, migrations, async connection
│   ├── models.py           # Pydantic request/response models
│   ├── auth.py             # JWT + bcrypt helpers
│   ├── services.py         # Shared business logic
│   ├── audit.py            # Audit log recording
│   ├── notifications.py    # Email/SMS (optional, requires config)
│   ├── config.py           # Environment variables and paths
│   ├── init_db.py          # DB init script
│   ├── seed_slots.py       # Seed parking slots
│   ├── seed_lots.py        # Seed parking lots
│   └── routes/
│       ├── auth.py         # /api/auth/*
│       ├── slots.py        # /api/slots/*
│       ├── reservations.py # /api/reservations/*
│       ├── cars.py         # /api/cars/*
│       ├── payments.py     # /api/payments/*
│       ├── admin.py        # /api/admin/*
│       ├── chat.py         # /api/chat
│       └── lots.py         # /api/lots
│
├── ai_module/
│   └── inference.py        # YOLO detection loop, slot update sender
│
├── frontend/
│   ├── index.html          # Landing page
│   ├── dashboard.html      # User dashboard with live feed
│   ├── map.html            # Lot map view
│   ├── lot.html            # Single lot with slot overlay
│   ├── my-cars.html        # Vehicle management
│   ├── my-reservations.html
│   ├── account.html        # Profile settings
│   ├── admin.html          # Admin dashboard
│   ├── payment-methods.html
│   ├── checkout.html
│   ├── slots-editor.html   # Polygon calibration tool
│   └── static/
│       ├── css/styles.css
│       └── js/
│           ├── api.js      # API client wrapper
│           ├── app.js      # App logic and routing
│           ├── chat.js     # Chat widget
│           └── slot_editor.js
│
├── config/
│   ├── bmu.json            # Slot polygons for lot 1 (British School)
│   └── west.json           # Slot polygons for lot 2 (Westminster)
│
├── video/
│   ├── bmu.mp4             # Video feed for lot 1
│   ├── west.mp4            # Video feed for lot 2
│   ├── latest.jpg          # Latest frame lot 1 (auto-updated by AI)
│   └── latest-lot-2.jpg    # Latest frame lot 2
│
├── models/
│   └── yolo11m.pt          # YOLO model (auto-downloaded on first run)
│
├── database/
│   └── parking.db          # SQLite database (auto-created)
│
├── tools/                  # Diagnostic and test scripts
├── docs/                   # Additional guides
├── requirements.txt        # Backend dependencies
├── requirements-ai.txt     # AI module dependencies
└── run.py                  # Server entry point
 

-

- Quick Start

Recommended: Python 3.11 or 3.12.

  1. Set up environment

 bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
 

  2. Run the backend

 bash
python run.py
 

- App: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

The database, tables, and seed data are initialized automatically on first run.
Vision workers are started **inside** the FastAPI process for every `is_live` lot, so you
don't need to run a second process unless you want a standalone debug window.

  3. Run the AI module in a separate process (optional)

 bash
pip install -r requirements-ai.txt

# Lot 1 (British School)
python ai_module/inference.py --lot-id 1

# Lot 2 (Westminster)
python ai_module/inference.py --lot-id 2
 

The YOLO11m model downloads automatically on first run. Both lot instances can run simultaneously.
If you do this, set `PARKING_VISION_ENABLED=false` to avoid running two detectors against the
same lot.

-

- Default Admin Account

 
Phone:    +1234567890
Password: admin123
 

-

- Key API Endpoints

  Auth
  Method   Path   Description  

  POST   `/api/auth/register`   Register new user  
  POST   `/api/auth/login`   Login, returns JWT  
  GET   `/api/auth/me`   Get current user profile  
  PUT   `/api/auth/me`   Update profile  
  POST   `/api/auth/change-password`   Change password  

  Slots
  Method   Path   Description  

  GET   `/api/slots/status`   All slots (filter by `lot_id`)  
  GET   `/api/slots/stats`   Occupancy statistics  
  GET   `/api/slots/config`   Polygon config for a lot (filter by `lot_id`)  
  GET   `/api/slots/stream`   Server-Sent Events feed of slot updates  
  POST   `/api/slots/update-status`   AI module update (requires `X-API-Key`, body may include `lot_id` per row)  

  Reservations
  Method   Path   Description  

  GET   `/api/reservations/my-reservations`   User's reservations  
  POST   `/api/reservations/create`   Create reservation  
  POST   `/api/reservations/confirm-payment`   Confirm payment  
  POST   `/api/reservations/{id}/cancel`   Cancel  

  Cars & Payments
  Method   Path   Description  

  GET/POST   `/api/cars/`   List / add vehicle  
  PUT/DELETE   `/api/cars/{id}`   Update / remove vehicle  
  GET/POST   `/api/payments/methods`   List / add payment method  
  DELETE   `/api/payments/methods/{id}`   Remove payment method  

  Admin
  Method   Path   Description  

  GET   `/api/admin/stats`   System overview stats  
  GET   `/api/admin/users`   All users  
  PATCH   `/api/admin/users/{id}`   Enable/disable user  
  GET   `/api/admin/reservations`   All reservations  
  GET   `/api/admin/analytics/reservations-by-day`   Reservations chart  
  GET   `/api/admin/analytics/top-slots`   Most booked slots  
  GET   `/api/admin/audit-log`   Action audit trail  



- Configuration

  Environment variables (`.env` or shell)

 env
SECRET_KEY=your-secret-key
DEBUG=True
HOST=127.0.0.1
PORT=8000
DATABASE_PATH=database/parking.db
AI_API_KEY=ai-module-secret-key-12345

# chat assistant
CHAT_ENABLED=true
OPENAI_API_KEY=sk-...

# email notifications
NOTIFY_EMAIL_ENABLED=false
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=...

# SMS notifications (Twilio)
NOTIFY_SMS_ENABLED=false
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
 

The `AI_API_KEY` must match between the backend and the AI module — the AI module sends it as the `X-API-Key` header when posting slot updates.

  Slot polygon configuration

Edit `config/bmu.json` (lot 1) or `config/west.json` (lot 2) to define slot boundaries:

 json
{
  "A1": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
  "A2": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
}
 

Use the built-in **Slot Editor** (`/slots-editor.html`) to draw and adjust polygons visually.


- Pre-seeded Parking Lots

  1   British School of Tashkent   A1–A5 (5 slots)   `bmu.mp4`  
  2   Westminster International University   W1–W5 (5 slots)   `west.mp4`  



- Additional Resources

- `docs/` — setup guides, notification config, roadmap
- `tools/` — diagnostic scripts (`check_setup.py`, `check_database.py`, `check_slots.py`)
- `http://localhost:8000/docs` — interactive Swagger API documentation

