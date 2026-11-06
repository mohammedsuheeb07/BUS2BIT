import os
import hmac
import html
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    render_template_string,
    jsonify,
    session,
)

app = Flask(__name__)

DATABASE = "bus2bit_v2.db"

# Set SECRET_KEY in Render. A temporary key is used only if it is missing;
# sessions will reset whenever the app restarts until a permanent key is set.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "false").lower() == "true"
)


# ---------------- DATABASE ----------------

def get_db():
    connection = sqlite3.connect(DATABASE, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_number TEXT UNIQUE NOT NULL,
            route_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active'
        )
    """)

    connection.execute("""
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

    # Ensure BUS-01 through BUS-14 exist. Existing records are not overwritten.
    default_buses = [
        ("BUS-01", "College Route 1", "Active"),
        ("BUS-02", "College Route 2", "Active"),
        ("BUS-03", "College Route 3", "Active"),
        ("BUS-04", "College Route 4", "Active"),
        ("BUS-05", "College Route 5", "Active"),
        ("BUS-06", "College Route 6", "Active"),
        ("BUS-07", "College Route 7", "Active"),
        ("BUS-08", "College Route 8", "Active"),
        ("BUS-09", "College Route 9", "Active"),
        ("BUS-10", "College Route 10", "Active"),
        ("BUS-11", "College Route 11", "Active"),
        ("BUS-12", "College Route 12", "Active"),
        ("BUS-13", "College Route 13", "Active"),
        ("BUS-14", "College Route 14", "Active"),
    ]

    connection.executemany("""
        INSERT OR IGNORE INTO buses (bus_number, route_name, status)
        VALUES (?, ?, ?)
    """, default_buses)

    connection.commit()
    connection.close()


# ---------------- COMMON SECURITY HELPERS ----------------

def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def csrf_field():
    # Token is generated from hexadecimal characters, so it is safe in this value.
    token = get_csrf_token()
    return f'<input type="hidden" name="csrf_token" value="{token}">'


def valid_csrf_token():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))

        if request.method == "POST" and not valid_csrf_token():
            return "Security check failed. Refresh the page and try again.", 400

        return function(*args, **kwargs)

    return wrapper


# ---------------- COMMON PAGE DESIGN ----------------

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#102747">
    <title>BUS2BIT | Smart College Bus Tracking</title>

    <style>
        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f1f5f9;
            color: #172033;
        }

        header {
            background: #102747;
            color: white;
            padding: 24px 7%;
        }

        header h1 { margin: 0 0 8px; }

        main {
            max-width: 1100px;
            margin: 30px auto;
            padding: 0 20px;
        }

        .card {
            background: white;
            padding: 24px;
            margin-bottom: 20px;
            border-radius: 12px;
            box-shadow: 0 3px 12px #0000000d;
            overflow-x: auto;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 18px;
        }

        input, select {
            box-sizing: border-box;
            width: 100%;
            padding: 12px;
            margin: 7px 0 16px;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
        }

        button, .button {
            display: inline-block;
            border: 0;
            border-radius: 6px;
            padding: 11px 16px;
            background: #1769d2;
            color: white;
            text-decoration: none;
            cursor: pointer;
            font-size: 14px;
        }

        .green { background: #16804a; }
        .red { background: #c63737; }
        .gray { background: #64748b; }

        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            min-width: 520px;
        }

        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }

        .message {
            background: #dcfce7;
            padding: 12px;
            border-radius: 6px;
        }

        footer {
            text-align: center;
            padding: 25px;
            color: #64748b;
        }

        .muted { color: #64748b; }
        .top-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        form.inline-form { display: inline; }
    </style>
</head>

<body>
<header>
    <h1>🚌 BUS2BIT</h1>
    <div>Smart College Bus Tracking System</div>
</header>

<main>
    {{ content|safe }}
</main>

<footer>BUS2BIT — Smart College Bus Tracking Project</footer>
</body>
</html>
"""


def page(content):
    return render_template_string(PAGE, content=content)


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    content = """
    <section class="card">
        <h2>Welcome to BUS2BIT</h2>
        <p>
            Find college buses and help authorised administrators manage buses
            and their dedicated GPS devices.
        </p>

        <div class="top-actions">
            <a class="button green" href="/student">🎓 Student Mode</a>
            <a class="button" href="/admin">🛠️ Admin Mode</a>
        </div>
    </section>
    """
    return page(content)


# ---------------- ADMIN LOGIN AND LOGOUT ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin"))

    error = ""

    if request.method == "POST":
        if not valid_csrf_token():
            return "Security check failed. Refresh the page and try again.", 400

        expected_username = os.environ.get("ADMIN_USERNAME", "admin")
        expected_password = os.environ.get("ADMIN_PASSWORD", "")

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if not expected_password:
            return "Admin password is not configured in the server environment.", 503

        username_ok = hmac.compare_digest(username, expected_username)
        password_ok = hmac.compare_digest(password, expected_password)

        if username_ok and password_ok:
            session.clear()
            session["is_admin"] = True
            get_csrf_token()
            return redirect(url_for("admin"))

        error = "Incorrect username or password."

    content = f"""
    <section class="card">
        <h2>🔐 Admin Login</h2>
        <p class="muted">Authorised administrators only.</p>
        <p style="color:#c63737;">{html.escape(error)}</p>

        <form method="post" action="/admin/login">
            {csrf_field()}
            <label>Username</label>
            <input name="username" autocomplete="username" required>

            <label>Password</label>
            <input name="password" type="password"
                   autocomplete="current-password" required>

            <button class="green" type="submit">Login</button>
        </form>

        <p><a href="/">← Back to Home</a></p>
    </section>
    """
    return page(content)


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


# ---------------- STUDENT MODE ----------------

@app.route("/student")
def student():
    connection = get_db()

    buses = connection.execute("""
        SELECT
            b.bus_number,
            b.route_name,
            b.status,
            g.latitude,
            g.longitude,
            g.last_updated
        FROM buses b
        LEFT JOIN gps_devices g
            ON b.bus_number = g.bus_number
        ORDER BY b.bus_number
    """).fetchall()

    connection.close()

    cards = ""

    for bus in buses:
        bus_number = html.escape(str(bus["bus_number"]))
        route_name = html.escape(str(bus["route_name"]))
        status = html.escape(str(bus["status"]))

        location = "GPS location not available yet"
        if bus["latitude"] is not None and bus["longitude"] is not None:
            location = (
                f'Latitude: {html.escape(str(bus["latitude"]))}, '
                f'Longitude: {html.escape(str(bus["longitude"]))}'
            )

        last_updated = html.escape(
            str(bus["last_updated"] or "No location received")
        )

        cards += f"""
        <article class="card">
            <h3>🚌 {bus_number}</h3>
            <p>Route: {route_name}</p>
            <p>Status: {status}</p>
            <p>{location}</p>
            <p class="muted">Last update: {last_updated}</p>
        </article>
        """

    content = f"""
    <section class="card">
        <h2>🎓 Student Dashboard</h2>
        <p>Find your college bus and view its available GPS information.</p>
        <a class="button gray" href="/">← Back to Home</a>
    </section>

    <section class="card">
        <h2>🗺️ Live Bus Map</h2>
        <p id="map-message">Loading bus locations...</p>
        <div id="bus-map"
             style="height: 400px; width: 100%; border-radius: 12px;">
        </div>
    </section>

    <div class="grid">{cards}</div>

    <link rel="stylesheet"
          href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <script>
    document.addEventListener("DOMContentLoaded", function () {{
        const map = L.map("bus-map").setView([12.9141, 74.8560], 12);

        L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }}).addTo(map);

        const markers = {{}};
        const message = document.getElementById("map-message");

        async function refreshBusLocations() {{
            try {{
                const response = await fetch("/api/bus-locations");

                if (!response.ok) {{
                    throw new Error("Could not load bus locations");
                }}

                const buses = await response.json();
                let validLocations = 0;

                buses.forEach(function (bus) {{
                    if (bus.latitude == null || bus.longitude == null) {{
                        return;
                    }}

                    const lat = Number(bus.latitude);
                    const lon = Number(bus.longitude);

                    if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
                        lat < -90 || lat > 90 ||
                        lon < -180 || lon > 180) {{
                        return;
                    }}

                    validLocations++;

                    const popup = document.createElement("div");
                    const busTitle = document.createElement("strong");
                    busTitle.textContent = String(bus.bus_number);
                    popup.appendChild(busTitle);
                    popup.appendChild(document.createElement("br"));
                    popup.appendChild(document.createTextNode(String(bus.route_name)));
                    popup.appendChild(document.createElement("br"));
                    popup.appendChild(document.createTextNode(
                        "Status: " + String(bus.status)
                    ));

                    if (markers[bus.bus_number]) {{
                        markers[bus.bus_number]
                            .setLatLng([lat, lon])
                            .setPopupContent(popup);
                    }} else {{
                        markers[bus.bus_number] =
                            L.marker([lat, lon])
                                .addTo(map)
                                .bindPopup(popup);
                    }}
                }});

                message.textContent = validLocations > 0
                    ? validLocations + " bus location(s) available."
                    : "No GPS locations available yet. Waiting for GPS data.";

                if (validLocations > 0 && !map._busLocationsFitted) {{
                    const group = L.featureGroup(Object.values(markers));
                    map.fitBounds(group.getBounds(), {{padding: [30, 30]}});
                    map._busLocationsFitted = true;
                }}
            }} catch (error) {{
                message.textContent =
                    "Unable to load bus locations. Please try again shortly.";
                console.error(error);
            }}
        }}

        refreshBusLocations();
        setInterval(refreshBusLocations, 15000);
    }});
    </script>
    """

    return page(content)


# ---------------- ADMIN MODE ----------------

@app.route("/admin")
@admin_required
def admin():
    connection = get_db()

    buses = connection.execute(
        "SELECT * FROM buses ORDER BY bus_number"
    ).fetchall()

    devices = connection.execute(
        "SELECT * FROM gps_devices ORDER BY device_id"
    ).fetchall()

    connection.close()

    bus_rows = ""

    for bus in buses:
        bus_id = int(bus["id"])
        bus_number = html.escape(str(bus["bus_number"]))
        route_name = html.escape(str(bus["route_name"]))
        status = html.escape(str(bus["status"]))

        bus_rows += f"""
        <tr>
            <td>{bus_number}</td>
            <td>{route_name}</td>
            <td>{status}</td>
            <td>
                <form action="/delete-bus/{bus_id}" method="post"
                      onsubmit="return confirm('Delete this bus and its assigned GPS device records?')">
                    {csrf_field()}
                    <button class="red" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """

    device_rows = ""

    for device in devices:
        device_id = int(device["id"])
        shown_device_id = html.escape(str(device["device_id"]))
        shown_bus_number = html.escape(str(device["bus_number"]))
        device_status = html.escape(str(device["device_status"]))
        latitude = (
            html.escape(str(device["latitude"]))
            if device["latitude"] is not None else "—"
        )
        longitude = (
            html.escape(str(device["longitude"]))
            if device["longitude"] is not None else "—"
        )

        device_rows += f"""
        <tr>
            <td>{shown_device_id}</td>
            <td>{shown_bus_number}</td>
            <td>{device_status}</td>
            <td>{latitude}</td>
            <td>{longitude}</td>
            <td>
                <form action="/delete-device/{device_id}" method="post"
                      onsubmit="return confirm('Delete this GPS device?')">
                    {csrf_field()}
                    <button class="red" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """

    bus_options = ""

    for bus in buses:
        bus_number = html.escape(str(bus["bus_number"]), quote=True)
        route_name = html.escape(str(bus["route_name"]))
        bus_options += (
            f'<option value="{bus_number}">'
            f'{bus_number} — {route_name}</option>'
        )

    content = f"""
    <section class="card">
        <h2>🛠️ Admin Dashboard</h2>
        <p>Manage buses and register their GPS devices.</p>
        <div class="top-actions">
            <a class="button gray" href="/">← Back to Home</a>
            <form class="inline-form" action="/admin/logout" method="post">
                {csrf_field()}
                <button class="red" type="submit">Logout</button>
            </form>
        </div>
    </section>

    <section class="card">
        <h2>Add a New Bus</h2>

        <form action="/add-bus" method="post">
            {csrf_field()}
            <label>Bus Number</label>
            <input name="bus_number" placeholder="Example: BUS-15" required>

            <label>Route Name</label>
            <input name="route_name"
                   placeholder="Example: College Route 15" required>

            <label>Bus Status</label>
            <select name="status">
                <option>Active</option>
                <option>Inactive</option>
            </select>

            <button class="green" type="submit">+ Add Bus</button>
        </form>
    </section>

    <section class="card">
        <h2>Registered Buses ({len(buses)})</h2>

        <table>
            <tr>
                <th>Bus</th><th>Route</th><th>Status</th><th>Action</th>
            </tr>
            {bus_rows}
        </table>
    </section>

    <section class="card">
        <h2>🛰️ Register a GPS Device</h2>

        <p class="muted">
            Enter the unique ID of a compatible GPS tracker installed in a bus.
            This registers the device; it does not connect to the hardware yet.
        </p>

        <form action="/add-device" method="post">
            {csrf_field()}
            <label>GPS Device ID</label>
            <input name="device_id"
                   placeholder="Example: GPS-BUS-01" required>

            <label>Assign to Bus</label>
            <select name="bus_number" required>
                <option value="">Select a bus</option>
                {bus_options}
            </select>

            <button type="submit">+ Register GPS Device</button>
        </form>
    </section>

    <section class="card">
        <h2>Registered GPS Devices ({len(devices)})</h2>

        <table>
            <tr>
                <th>Device ID</th><th>Bus</th><th>Status</th>
                <th>Latitude</th><th>Longitude</th><th>Action</th>
            </tr>
            {device_rows}
        </table>
    </section>
    """

    return page(content)


# ---------------- ADD BUS ----------------

@app.route("/add-bus", methods=["POST"])
@admin_required
def add_bus():
    bus_number = request.form.get("bus_number", "").strip().upper()
    route_name = request.form.get("route_name", "").strip()
    status = request.form.get("status", "Active")

    if not bus_number or not route_name:
        return "Bus number and route name are required.", 400

    if status not in ("Active", "Inactive"):
        return "Invalid bus status.", 400

    connection = get_db()

    try:
        connection.execute("""
            INSERT INTO buses (bus_number, route_name, status)
            VALUES (?, ?, ?)
        """, (bus_number, route_name, status))
        connection.commit()

    except sqlite3.IntegrityError:
        connection.close()
        return "That bus number already exists. Go back and try another.", 400

    connection.close()
    return redirect(url_for("admin"))


# ---------------- DELETE BUS ----------------

@app.route("/delete-bus/<int:bus_id>", methods=["POST"])
@admin_required
def delete_bus(bus_id):
    connection = get_db()

    bus = connection.execute(
        "SELECT bus_number FROM buses WHERE id = ?", (bus_id,)
    ).fetchone()

    if bus:
        connection.execute(
            "DELETE FROM gps_devices WHERE bus_number = ?",
            (bus["bus_number"],)
        )
        connection.execute("DELETE FROM buses WHERE id = ?", (bus_id,))
        connection.commit()

    connection.close()
    return redirect(url_for("admin"))


# ---------------- REGISTER GPS DEVICE ----------------

@app.route("/add-device", methods=["POST"])
@admin_required
def add_device():
    device_id = request.form.get("device_id", "").strip()
    bus_number = request.form.get("bus_number", "").strip()

    if not device_id:
        return "GPS device ID is required.", 400

    connection = get_db()

    bus = connection.execute(
        "SELECT bus_number FROM buses WHERE bus_number = ?",
        (bus_number,)
    ).fetchone()

    if not bus:
        connection.close()
        return "Please select a valid bus.", 400

    try:
        connection.execute("""
            INSERT INTO gps_devices (device_id, bus_number)
            VALUES (?, ?)
        """, (device_id, bus_number))
        connection.commit()

    except sqlite3.IntegrityError:
        connection.close()
        return (
            "This GPS device ID is already registered. "
            "Go back and enter a unique ID.",
            400
        )

    connection.close()
    return redirect(url_for("admin"))


# ---------------- DELETE GPS DEVICE ----------------

@app.route("/delete-device/<int:device_id>", methods=["POST"])
@admin_required
def delete_device(device_id):
    connection = get_db()

    connection.execute(
        "DELETE FROM gps_devices WHERE id = ?", (device_id,)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("admin"))


# ---------------- GPS LOCATION UPDATE API ----------------
# GPS_UPDATE_TOKEN must be configured as a Render environment variable.
# A tracker or trusted gateway must send this token in X-GPS-Token.

@app.route("/api/gps-update", methods=["POST"])
def gps_update():
    expected_token = os.environ.get("GPS_UPDATE_TOKEN", "")
    supplied_token = request.headers.get("X-GPS-Token", "")

    if not expected_token or not hmac.compare_digest(
        supplied_token, expected_token
    ):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    try:
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": "Provide numeric latitude and longitude."
        }), 400

    if not (-90 <= latitude <= 90):
        return jsonify({"error": "Latitude must be between -90 and 90."}), 400

    if not (-180 <= longitude <= 180):
        return jsonify({"error": "Longitude must be between -180 and 180."}), 400

    if not device_id:
        return jsonify({"error": "GPS device ID is required."}), 400

    connection = get_db()

    device = connection.execute(
        "SELECT id FROM gps_devices WHERE device_id = ?",
        (device_id,)
    ).fetchone()

    if not device:
        connection.close()
        return jsonify({"error": "GPS device is not registered."}), 404

    connection.execute("""
        UPDATE gps_devices
        SET latitude = ?, longitude = ?, last_updated = ?
        WHERE device_id = ?
    """, (
        latitude,
        longitude,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        device_id
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "message": "Location saved successfully.",
        "device_id": device_id,
        "latitude": latitude,
        "longitude": longitude
    })


# ---------------- BUS MAP DATA API ----------------

@app.route("/api/bus-locations")
def bus_locations():
    connection = get_db()

    buses = connection.execute("""
        SELECT
            b.bus_number,
            b.route_name,
            b.status,
            g.latitude,
            g.longitude,
            g.last_updated
        FROM buses b
        LEFT JOIN gps_devices g
            ON b.bus_number = g.bus_number
        ORDER BY b.bus_number
    """).fetchall()

    connection.close()

    results = []

    for bus in buses:
        results.append({
            "bus_number": bus["bus_number"],
            "route_name": bus["route_name"],
            "status": bus["status"],
            "latitude": bus["latitude"],
            "longitude": bus["longitude"],
            "last_updated": bus["last_updated"]
        })

    return jsonify(results)


# ---------------- START APPLICATION ----------------

initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
