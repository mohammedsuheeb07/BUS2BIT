import os
import hmac
from flask import Flask, request, redirect, url_for, render_template_string,jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "bus2bit_v2.db"


# ---------------- DATABASE ----------------

def get_db():
    connection = sqlite3.connect(DATABASE)
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

    # Add demonstration buses only when the new database is empty.
    count = connection.execute(
        "SELECT COUNT(*) FROM buses"
    ).fetchone()[0]

    if count == 0:
        connection.executemany("""
            INSERT INTO buses (bus_number, route_name, status)
            VALUES (?, ?, ?)
        """, [
            ("BUS-01", "College Route 1", "Active"),
            ("BUS-02", "College Route 2", "Active"),
            ("BUS-03", "College Route 3", "Inactive")
        ])

    connection.commit()
    connection.close()


# ---------------- COMMON PAGE DESIGN ----------------

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>BUS2BIT | Smart College Bus Tracking</title>

    <style>
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
        }

        .green { background: #16804a; }
        .red { background: #c63737; }
        .gray { background: #64748b; }

        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
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
            Find college buses and help administrators manage buses
            and their dedicated GPS devices.
        </p>

        <a class="button green" href="/student">🎓 Student Mode</a>
        <a class="button" href="/admin">🛠️ Admin Mode</a>
    </section>
    """
    return page(content)


# ---------------- STUDENT MODE ----------------

@app.route("/student")
def student():
    connection = get_db()

    buses = connection.execute("""
        SELECT b.*,
               g.latitude,
               g.longitude,
               g.last_updated
        FROM buses b
        LEFT JOIN gps_devices g
          ON b.bus_number = g.bus_number
    """).fetchall()

    connection.close()

    cards = ""

    for bus in buses:
        location = "GPS location not available yet"

        if bus["latitude"] is not None and bus["longitude"] is not None:
            location = (
                f'Latitude: {bus["latitude"]}, '
                f'Longitude: {bus["longitude"]}'
            )

        cards += f"""
        <article class="card">
            <h3>🚌 {bus['bus_number']}</h3>
            <p>Route: {bus['route_name']}</p>
            <p>Status: {bus['status']}</p>
            <p>{location}</p>
            <p class="muted">
                Last update: {bus['last_updated'] or 'No location received'}
            </p>
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

                    const popup =
                        "<b>" + String(bus.bus_number) + "</b><br>" +
                        String(bus.route_name) + "<br>" +
                        "Status: " + String(bus.status);

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
        bus_rows += f"""
        <tr>
            <td>{bus['bus_number']}</td>
            <td>{bus['route_name']}</td>
            <td>{bus['status']}</td>
            <td>
                <form action="/delete-bus/{bus['id']}" method="post"
                      onsubmit="return confirm('Delete this bus?')">
                    <button class="red" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """

    device_rows = ""

    for device in devices:
        device_rows += f"""
        <tr>
            <td>{device['device_id']}</td>
            <td>{device['bus_number']}</td>
            <td>{device['device_status']}</td>
            <td>
                {device['latitude'] if device['latitude'] is not None else '—'}
            </td>
            <td>
                {device['longitude'] if device['longitude'] is not None else '—'}
            </td>
            <td>
                <form action="/delete-device/{device['id']}" method="post"
                      onsubmit="return confirm('Delete this GPS device?')">
                    <button class="red" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """

    bus_options = ""

    for bus in buses:
        bus_options += (
            f'<option value="{bus["bus_number"]}">'
            f'{bus["bus_number"]} — {bus["route_name"]}</option>'
        )

    content = f"""
    <section class="card">
        <h2>🛠️ Admin Dashboard</h2>
        <p>Manage demonstration buses and register their GPS devices.</p>
        <a class="button gray" href="/">← Back to Home</a>
    </section>

    <section class="card">
        <h2>Add a New Bus</h2>

        <form action="/add-bus" method="post">
            <label>Bus Number</label>
            <input name="bus_number" placeholder="Example: BUS-04" required>

            <label>Route Name</label>
            <input name="route_name"
                   placeholder="Example: College Route 4" required>

            <label>Bus Status</label>
            <select name="status">
                <option>Active</option>
                <option>Inactive</option>
            </select>

            <button class="green" type="submit">+ Add Bus</button>
        </form>
    </section>

    <section class="card">
        <h2>Registered Buses</h2>

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
        <h2>Registered GPS Devices</h2>

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
def add_bus():
    bus_number = request.form["bus_number"].strip().upper()
    route_name = request.form["route_name"].strip()
    status = request.form["status"]

    if not bus_number or not route_name:
        return "Bus number and route name are required.", 400

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
def add_device():
    device_id = request.form["device_id"].strip()
    bus_number = request.form["bus_number"].strip()

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
def delete_device(device_id):
    connection = get_db()

    connection.execute(
        "DELETE FROM gps_devices WHERE id = ?", (device_id,)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("admin"))


# ---------------- DEMO LOCATION UPDATE ----------------
# This endpoint is for testing only.
# Real GPS integration will require device authentication.

@app.route("/api/gps-update", methods=["POST"])
def gps_update():
    expected_token = os.environ.get("GPS_UPDATE_TOKEN", "")
    supplied_token = request.headers.get("X-GPS-Token", "")

    if not expected_token or not hmac.compare_digest(
        supplied_token, expected_token
    ):
        return {"error": "Unauthorized"}, 401

    data = request.get_json(silent=True) or {} 

    device_id = str(data.get("device_id", "")).strip()

    try:
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return {
            "error": "Provide numeric latitude and longitude."
        }, 400

    if not (-90 <= latitude <= 90):
        return {"error": "Latitude must be between -90 and 90."}, 400

    if not (-180 <= longitude <= 180):
        return {"error": "Longitude must be between -180 and 180."}, 400

    connection = get_db()

    device = connection.execute(
        "SELECT id FROM gps_devices WHERE device_id = ?",
        (device_id,)
    ).fetchone()

    if not device:
        connection.close()
        return {"error": "GPS device is not registered."}, 404

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

    return {
        "message": "Demo location saved successfully.",
        "device_id": device_id,
        "latitude": latitude,
        "longitude": longitude
    }

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

# ---------------- START APPLICATION ----------------

initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
