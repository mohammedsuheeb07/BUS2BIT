import os
import hmac
import html
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template_string,
    request, session, url_for
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "false").lower() == "true"
)

DATABASE = os.environ.get("DATABASE_PATH", "bus2bit_v2.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

DEFAULT_BUSES = [
    (f"BUS-{number:02d}", "Route not assigned", "Active")
    for number in range(1, 15)
]

# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def get_db():
    connection = sqlite3.connect(DATABASE, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS buses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_number TEXT UNIQUE NOT NULL,
                route_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active'
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS gps_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE NOT NULL,
                bus_number TEXT NOT NULL,
                device_status TEXT NOT NULL DEFAULT 'Registered',
                latitude REAL,
                longitude REAL,
                last_updated TEXT
            )
        """)
        db.executemany(
            """INSERT OR IGNORE INTO buses (bus_number, route_name, status)
               VALUES (?, ?, ?)""",
            DEFAULT_BUSES
        )
        db.commit()


# ---------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------

def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_valid():
    supplied = request.form.get("_csrf_token", "")
    expected = session.get("_csrf_token", "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


def require_csrf():
    if not csrf_valid():
        abort(400, description="The form expired or could not be verified. Please go back and try again.")


def admin_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return decorated


@app.context_processor
def inject_template_helpers():
    return {"csrf_token": csrf_token}


# ---------------------------------------------------------------------
# Student interface - this is the public home page.
# No Admin Mode link or admin login link is shown here.
# ---------------------------------------------------------------------

STUDENT_PAGE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BUS2BIT | College Bus Tracking</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root { color-scheme: light; --green:#13834a; --dark:#10251b; --muted:#64746b; --bg:#f4f8f5; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Arial, sans-serif; background:var(--bg); color:var(--dark); }
    header { background:#fff; border-bottom:1px solid #e3ebe5; padding:15px 5%; display:flex; align-items:center; gap:12px; }
    .logo { width:42px; height:42px; border-radius:13px; display:grid; place-items:center; background:#e2f5e9; color:var(--green); font-size:23px; }
    header h1 { margin:0; font-size:21px; }
    header small { color:var(--muted); }
    main { max-width:1100px; margin:28px auto; padding:0 16px 35px; }
    .hero { background:linear-gradient(120deg,#0e7541,#20a65f); color:white; border-radius:22px; padding:26px; }
    .hero h2 { margin:0 0 8px; font-size:clamp(24px,4vw,34px); }
    .hero p { margin:0; opacity:.92; }
    .searchbox { margin-top:20px; display:flex; gap:10px; background:#fff; border-radius:14px; padding:8px; }
    .searchbox input { min-width:0; flex:1; border:0; outline:0; padding:12px; font-size:16px; color:#173323; }
    button { border:0; border-radius:10px; background:#117a43; color:#fff; padding:12px 19px; font-weight:bold; cursor:pointer; }
    .section-title { margin:25px 0 12px; font-size:19px; }
    #results { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
    .bus-card { background:#fff; border:1px solid #e3ebe5; border-radius:15px; padding:16px; text-align:left; cursor:pointer; color:var(--dark); }
    .bus-card:hover { border-color:#53ae78; box-shadow:0 4px 15px #163d2510; }
    .bus-card strong { display:block; font-size:17px; margin-bottom:7px; }
    .route { color:var(--muted); font-size:14px; }
    .status { display:inline-block; margin-top:12px; font-size:12px; padding:5px 9px; border-radius:20px; background:#e4f7eb; color:#13753f; }
    .status.inactive { background:#fce9e9; color:#a32b2b; }
    #map { height:390px; border-radius:17px; overflow:hidden; border:1px solid #dce7df; background:#e9efeb; }
    .hint { color:var(--muted); font-size:13px; margin-top:10px; }
    .empty { background:#fff; border:1px dashed #cbd9cf; border-radius:14px; padding:20px; color:var(--muted); }
    footer { text-align:center; padding:20px; color:#748078; font-size:12px; }
    @media(max-width:560px) { .hero { padding:20px; } .searchbox { flex-direction:column; } .searchbox button { width:100%; } #map { height:320px; } }
  </style>
</head>
<body>
<header>
  <div class="logo">🚌</div>
  <div><h1>BUS2BIT</h1><small>BEARYS Institute of Technology</small></div>
</header>
<main>
  <section class="hero">
    <h2>Find your college bus</h2>
    <p>Search your route and check your bus location.</p>
    <form class="searchbox" id="searchForm">
      <input id="routeSearch" type="search" placeholder="Enter route name (e.g. Mangaluru)" autocomplete="off">
      <button type="submit">Search buses</button>
    </form>
  </section>

  <h3 class="section-title">Available buses</h3>
  <div id="results"><div class="empty">Loading buses…</div></div>

  <h3 class="section-title">Bus location map</h3>
  <div id="map"></div>
  <p class="hint">Bus locations refresh automatically every 15 seconds. A bus appears on the map after its GPS device sends a location.</p>
</main>
<footer>BUS2BIT · Smart College Bus Tracking System</footer>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map').setView([12.9141, 74.8560], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  let allBuses = [];
  const markers = {};

  function safeText(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    })[ch]);
  }

  function renderBuses() {
    const term = document.getElementById('routeSearch').value.trim().toLowerCase();
    const filtered = allBuses.filter(bus =>
      !term ||
      (bus.route_name || '').toLowerCase().includes(term) ||
      (bus.bus_number || '').toLowerCase().includes(term)
    );
    const results = document.getElementById('results');
    if (!filtered.length) {
      results.innerHTML = '<div class="empty">No buses match that route. Check the spelling or try another route name.</div>';
      return;
    }
    results.innerHTML = filtered.map(bus => `
      <button type="button" class="bus-card" data-bus="${safeText(bus.bus_number)}">
        <strong>${safeText(bus.bus_number)}</strong>
        <span class="route">${safeText(bus.route_name || 'Route not assigned')}</span><br>
        <span class="status ${bus.status === 'Active' ? '' : 'inactive'}">${safeText(bus.status || 'Unknown')}</span>
        <span class="route">${bus.latitude != null && bus.longitude != null ? ' · GPS location available' : ' · Waiting for GPS'}</span>
      </button>
    `).join('');
    results.querySelectorAll('[data-bus]').forEach(button => {
      button.addEventListener('click', () => {
        const selected = allBuses.find(bus => bus.bus_number === button.dataset.bus);
        if (selected && selected.latitude != null && selected.longitude != null) {
          map.setView([selected.latitude, selected.longitude], 16);
          if (markers[selected.bus_number]) markers[selected.bus_number].openPopup();
        } else {
          alert('The GPS location for this bus has not been received yet.');
        }
      });
    });
  }

  async function loadBuses() {
    try {
      const response = await fetch('/api/bus-locations', {cache:'no-store'});
      if (!response.ok) throw new Error('Could not load buses');
      allBuses = await response.json();
      allBuses.forEach(bus => {
        if (bus.latitude == null || bus.longitude == null) return;
        const position = [bus.latitude, bus.longitude];
        const popup = `<b>${safeText(bus.bus_number)}</b><br>${safeText(bus.route_name || '')}<br>Updated: ${safeText(bus.last_updated || 'Unknown')}`;
        if (markers[bus.bus_number]) {
          markers[bus.bus_number].setLatLng(position).setPopupContent(popup);
        } else {
          markers[bus.bus_number] = L.marker(position).addTo(map).bindPopup(popup);
        }
      });
      renderBuses();
    } catch (error) {
      document.getElementById('results').innerHTML =
        '<div class="empty">Unable to load buses right now. Please refresh the page.</div>';
    }
  }

  document.getElementById('searchForm').addEventListener('submit', event => {
    event.preventDefault();
    renderBuses();
  });
  document.getElementById('routeSearch').addEventListener('input', renderBuses);
  loadBuses();
  setInterval(loadBuses, 15000);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(STUDENT_PAGE)


@app.route("/student")
def student():
    # Keep the old student URL working, but make the public home page the main entry.
    return redirect(url_for("home"))


# ---------------------------------------------------------------------
# Admin login and dashboard
# ---------------------------------------------------------------------

LOGIN_PAGE = r"""
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BUS2BIT Admin Login</title>
<style>
body{margin:0;background:#f3f7f4;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh;color:#173323}
.card{background:white;width:min(92%,390px);padding:28px;border-radius:18px;box-shadow:0 8px 35px #17332312}
h2{margin-top:0}.muted{color:#68776e;font-size:14px}
label{display:block;margin:16px 0 6px;font-size:14px;font-weight:bold}
input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #ccd9cf;border-radius:9px;font-size:16px}
button{margin-top:20px;width:100%;padding:13px;border:0;border-radius:9px;background:#13834a;color:white;font-weight:bold;font-size:15px}
.error{color:#a22;margin:10px 0}.flash{padding:9px;background:#fcecec;border-radius:8px;margin:8px 0}
</style></head><body><main class="card">
<h2>BUS2BIT Admin</h2><p class="muted">Sign in to manage buses and GPS devices.</p>
{% with messages = get_flashed_messages() %}{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}
<form method="post">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<label for="username">Username</label><input id="username" name="username" required autocomplete="username">
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password">
<button type="submit">Login</button>
</form></main></body></html>
"""

ADMIN_PAGE = r"""
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BUS2BIT Admin Dashboard</title>
<style>
body{margin:0;background:#f4f8f5;color:#173323;font-family:Arial,sans-serif}
header{background:#fff;padding:16px 5%;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e1e9e3}
main{max-width:1050px;margin:25px auto;padding:0 15px}
.card{background:#fff;border:1px solid #e0e9e2;border-radius:15px;padding:18px;margin-bottom:17px}
h2{margin-top:0}h3{margin-top:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
label{display:block;font-size:13px;margin:10px 0 5px}
input,select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd8ce;border-radius:8px}
button,.button{display:inline-block;border:0;border-radius:8px;background:#13834a;color:white;padding:10px 14px;text-decoration:none;cursor:pointer}
.danger{background:#a93232}.muted{color:#68776e;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{text-align:left;padding:10px 7px;border-bottom:1px solid #e8eee9;vertical-align:top}
.flash{padding:10px;background:#e8f7ed;border-radius:8px;margin:8px 0}
.inline{display:inline}
@media(max-width:600px){table{font-size:12px}td,th{padding:8px 4px}}
</style></head><body>
<header><div><b>BUS2BIT Admin Dashboard</b><div class="muted">Manage routes, buses and GPS devices</div></div>
<form method="post" action="{{ url_for('admin_logout') }}"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><button type="submit">Logout</button></form>
</header><main>
{% with messages = get_flashed_messages() %}{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}
<section class="card"><h2>Bus management</h2>
<form method="post" action="{{ url_for('add_bus') }}">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<div class="grid">
<div><label>Bus number</label><input name="bus_number" placeholder="BUS-15" required></div>
<div><label>Route name</label><input name="route_name" placeholder="e.g. Mangaluru - Surathkal" required></div>
<div><label>Status</label><select name="status"><option>Active</option><option>Inactive</option></select></div>
</div><p><button type="submit">Add bus</button></p></form>
<table><thead><tr><th>Bus</th><th>Route</th><th>Status</th><th>Action</th></tr></thead><tbody>
{% for bus in buses %}<tr><td>{{ bus['bus_number'] }}</td><td>{{ bus['route_name'] }}</td><td>{{ bus['status'] }}</td><td>
<form class="inline" method="post" action="{{ url_for('delete_bus', bus_id=bus['id']) }}" onsubmit="return confirm('Delete this bus?')">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><button class="danger" type="submit">Delete</button></form></td></tr>{% endfor %}
</tbody></table></section>

<section class="card"><h2>GPS device management</h2>
<form method="post" action="{{ url_for('add_device') }}">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<div class="grid">
<div><label>Device ID</label><input name="device_id" placeholder="Enter device ID" required></div>
<div><label>Assigned bus</label><select name="bus_number" required>{% for bus in buses %}<option value="{{ bus['bus_number'] }}">{{ bus['bus_number'] }} — {{ bus['route_name'] }}</option>{% endfor %}</select></div>
<div><label>Device status</label><select name="device_status"><option>Registered</option><option>Coming soon</option><option>Inactive</option></select></div>
</div><p><button type="submit">Register GPS device</button></p></form>
<table><thead><tr><th>Device ID</th><th>Bus</th><th>Status</th><th>Last update</th><th>Action</th></tr></thead><tbody>
{% for device in devices %}<tr><td>{{ device['device_id'] }}</td><td>{{ device['bus_number'] }}</td><td>{{ device['device_status'] }}</td>
<td>{{ device['last_updated'] or 'No GPS update yet' }}</td><td>
<form class="inline" method="post" action="{{ url_for('delete_device', device_id=device['id']) }}" onsubmit="return confirm('Delete this GPS device?')">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><button class="danger" type="submit">Delete</button></form></td></tr>{% endfor %}
</tbody></table></section>
<p class="muted">Student tracking page: <a href="{{ url_for('home') }}">Open BUS2BIT</a></p>
</main></body></html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        require_csrf()
        if not ADMIN_PASSWORD:
            abort(503, description="Admin login is not configured. Set ADMIN_PASSWORD in the hosting environment.")
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        username_ok = hmac.compare_digest(username, ADMIN_USERNAME)
        password_ok = hmac.compare_digest(password, ADMIN_PASSWORD)
        if username_ok and password_ok:
            session.clear()
            session["is_admin"] = True
            session["_csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("admin_dashboard"))
        flash("Invalid username or password.")
    return render_template_string(LOGIN_PAGE)


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    require_csrf()
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_db() as db:
        buses = db.execute("SELECT * FROM buses ORDER BY bus_number").fetchall()
        devices = db.execute("SELECT * FROM gps_devices ORDER BY bus_number").fetchall()
    return render_template_string(ADMIN_PAGE, buses=buses, devices=devices)


@app.route("/add-bus", methods=["POST"])
@admin_required
def add_bus():
    require_csrf()
    bus_number = request.form.get("bus_number", "").strip().upper()
    route_name = request.form.get("route_name", "").strip()
    status = request.form.get("status", "Active").strip()
    if not bus_number or not route_name:
        flash("Enter both bus number and route name.")
    else:
        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO buses (bus_number, route_name, status) VALUES (?, ?, ?)",
                    (bus_number, route_name, status)
                )
                db.commit()
            flash("Bus added successfully.")
        except sqlite3.IntegrityError:
            flash("That bus number already exists.")
    return redirect(url_for("admin_dashboard"))


@app.route("/delete-bus/<int:bus_id>", methods=["POST"])
@admin_required
def delete_bus(bus_id):
    require_csrf()
    with get_db() as db:
        bus = db.execute("SELECT bus_number FROM buses WHERE id = ?", (bus_id,)).fetchone()
        if bus:
            db.execute("DELETE FROM buses WHERE id = ?", (bus_id,))
            db.execute("DELETE FROM gps_devices WHERE bus_number = ?", (bus["bus_number"],))
            db.commit()
            flash("Bus and its linked GPS device records were deleted.")
    return redirect(url_for("admin_dashboard"))


@app.route("/add-device", methods=["POST"])
@admin_required
def add_device():
    require_csrf()
    device_id = request.form.get("device_id", "").strip()
    bus_number = request.form.get("bus_number", "").strip().upper()
    device_status = request.form.get("device_status", "Registered").strip()
    if not device_id or not bus_number:
        flash("Enter a device ID and select a bus.")
    else:
        try:
            with get_db() as db:
                bus_exists = db.execute(
                    "SELECT 1 FROM buses WHERE bus_number = ?", (bus_number,)
                ).fetchone()
                if not bus_exists:
                    flash("Selected bus was not found.")
                else:
                    db.execute(
                        """INSERT INTO gps_devices (device_id, bus_number, device_status)
                           VALUES (?, ?, ?)""",
                        (device_id, bus_number, device_status)
                    )
                    db.commit()
                    flash("GPS device registered successfully.")
        except sqlite3.IntegrityError:
            flash("That device ID is already registered.")
    return redirect(url_for("admin_dashboard"))


@app.route("/delete-device/<int:device_id>", methods=["POST"])
@admin_required
def delete_device(device_id):
    require_csrf()
    with get_db() as db:
        db.execute("DELETE FROM gps_devices WHERE id = ?", (device_id,))
        db.commit()
    flash("GPS device deleted.")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------
# GPS API - provider integration can be added after Tata/MERCYDA access
# is officially provided. Keep GPS_UPDATE_TOKEN unchanged in Render.
# ---------------------------------------------------------------------

@app.route("/api/gps-update", methods=["POST"])
def gps_update():
    expected_token = os.environ.get("GPS_UPDATE_TOKEN", "")
    supplied_token = request.headers.get("X-GPS-Token", "")
    if not expected_token or not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Valid latitude and longitude are required"}), 400

    if not device_id or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return jsonify({"success": False, "error": "Invalid device ID or coordinates"}), 400

    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as db:
        device = db.execute(
            "SELECT id FROM gps_devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not device:
            return jsonify({"success": False, "error": "Device is not registered"}), 404
        db.execute(
            """UPDATE gps_devices
               SET latitude = ?, longitude = ?, last_updated = ?
               WHERE device_id = ?""",
            (latitude, longitude, updated_at, device_id)
        )
        db.commit()

    return jsonify({"success": True, "message": "GPS location updated"})


@app.route("/api/bus-locations", methods=["GET"])
def bus_locations():
    with get_db() as db:
        rows = db.execute("""
            SELECT
                b.bus_number,
                b.route_name,
                b.status,
                g.latitude,
                g.longitude,
                g.last_updated
            FROM buses b
            LEFT JOIN gps_devices g ON g.bus_number = b.bus_number
            ORDER BY b.bus_number
        """).fetchall()

    return jsonify([
        {
            "bus_number": row["bus_number"],
            "route_name": row["route_name"],
            "status": row["status"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "last_updated": row["last_updated"],
        }
        for row in rows
    ])


@app.errorhandler(400)
def bad_request(error):
    return (
        "<h2>Request could not be verified</h2>"
        "<p>The form may have expired. Go back, refresh the page, and try again.</p>",
        400
    )


# Initialize tables on startup. Existing bus/device rows are retained.
initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
