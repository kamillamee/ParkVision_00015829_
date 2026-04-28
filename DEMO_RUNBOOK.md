# ParkVision — Demo Runbook

Three layers of access, all from this laptop. Set up once; on the day of the
defense you only need the primary path.

| Layer | Launcher | URL pattern | Use when |
|---|---|---|---|
| **App (always required)** | `start_demo.bat` | `http://localhost:8000` | Always. Must be running for any tunnel to work. |
| **Primary tunnel** | `start_ngrok.bat` | `https://xxxxx.ngrok-free.app` | Default. Share this URL with the committee. |
| **Backup tunnel** | `start_tunnel_backup.bat` | `https://random.trycloudflare.com` | If ngrok stops responding. |
| **Emergency LAN** | (just `start_demo.bat`) | `http://<your-laptop-LAN-IP>:8000` | If campus internet dies entirely. |

Login: **Phone** `+1234567890`  **Password** `admin123`

---

## One-time setup

1. **Install ngrok** (PowerShell):
   ```powershell
   winget install ngrok.ngrok
   ```
   Sign up at https://dashboard.ngrok.com/signup, copy your token, then:
   ```powershell
   ngrok config add-authtoken <YOUR_TOKEN>
   ```

2. **Install cloudflared** (PowerShell):
   ```powershell
   winget install Cloudflare.cloudflared
   ```

3. **Allow port 8000 through Windows Firewall** (only matters for LAN/phone access).
   First time you launch `start_demo.bat`, Windows pops up a firewall prompt — click **Allow access** for both Private *and* Public networks. If you missed it:
   ```powershell
   New-NetFirewallRule -DisplayName "ParkVision 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```

---

## T-30 minutes before walking in

1. Double-click **`start_demo.bat`**. Wait until you see:
   ```
   OK: PARKING_VISION started 2 lot worker(s)
   Uvicorn running on http://0.0.0.0:8000
   ```
2. Open `http://localhost:8000` → log in → click through Dashboard, Map, My Cars, Reservations, Admin. Confirm live video plays.
3. Double-click **`start_ngrok.bat`** in a second terminal. Copy the `https://*.ngrok-free.app` URL.
4. Open the ngrok URL in an **incognito window** (so you're testing as a fresh visitor) → log in → confirm live video plays.
   - First visit may show ngrok's "you are about to visit a tunnel" interstitial — click through. Subsequent visits skip it.
5. Note your laptop's LAN IP (`ipconfig` → `IPv4 Address`) on a sticky note in case of emergency.

---

## During the demo

**Primary path** — share / project the ngrok URL.

**If the ngrok URL stops loading:**
1. Ctrl+C the ngrok terminal.
2. Double-click **`start_tunnel_backup.bat`** → wait 3–5 s → copy the new `trycloudflare.com` URL → share it.

**If internet dies entirely (no ngrok, no cloudflared):**
1. Settings → Network → **Mobile hotspot → On**.
2. Have the committee laptop join your hotspot.
3. They open `http://<your-laptop-IP>:8000`. The IP shown in the `start_demo.bat` window updates when you toggle hotspot — recheck.

---

## Phone test (do this once before the day)

While `start_demo.bat` is running:

1. Connect your phone to the **same wifi as your laptop**.
2. On the laptop, look at the `start_demo.bat` window — it prints:
   ```
   Same wifi:    http://192.168.x.x:8000
   ```
3. Open that URL in your phone browser.
4. If it doesn't load: Windows Firewall is blocking. Run the `New-NetFirewallRule` command from the one-time setup.
5. The mobile responsive CSS should kick in automatically — hamburger menu top-left, stacked layout.

---

## Things to verify the day before

- [ ] `start_demo.bat` boots cleanly (no Python errors)
- [ ] `start_ngrok.bat` produces a working public URL
- [ ] `start_tunnel_backup.bat` produces a working public URL (then Ctrl+C — only run on the day if needed)
- [ ] Phone can reach `http://<laptop-LAN-IP>:8000` over wifi
- [ ] Live video plays smoothly over ngrok for 5+ minutes uninterrupted
   - If it stutters: edit `start_demo.bat`, change `PARKING_VISION_DETECT_FPS=4` to `2`
- [ ] Admin password is **changed** from the default `admin123` (your URL will be public for the duration)

---

## Useful commands while running

| Need | Command |
|---|---|
| Stop the app | Ctrl+C in the `start_demo.bat` window |
| See what's listening on 8000 | `netstat -ano \| findstr :8000` |
| Find your LAN IP | `ipconfig \| findstr IPv4` |
| Change admin password (one-liner) | see `README.md` or ask Claude |

---

## What to do **after** the defense

- Stop `start_demo.bat` (Ctrl+C) — closes the public tunnel automatically.
- Optionally rotate `AI_API_KEY` / change admin password back if you used a defense-only one.
- Nothing to "tear down" on a server because nothing was deployed to one.
