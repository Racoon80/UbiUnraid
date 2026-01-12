import json
import os
from typing import Dict, List, Optional, Tuple

import docker
import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

UNIFI_HOST = (os.environ.get("UNIFI_HOST") or "").rstrip("/")
UNIFI_USERNAME = os.environ.get("UNIFI_USERNAME") or ""
UNIFI_PASSWORD = os.environ.get("UNIFI_PASSWORD") or ""
UNIFI_SITE = os.environ.get("UNIFI_SITE", "default")
UNIFI_NETWORK_ID = os.environ.get("UNIFI_NETWORK_ID") or ""
VERIFY_SSL = os.environ.get("VERIFY_SSL", "false").lower() == "true"


def ensure_configured() -> Optional[str]:
    if not UNIFI_HOST or not UNIFI_USERNAME or not UNIFI_PASSWORD:
        return "UNIFI_HOST, UNIFI_USERNAME, and UNIFI_PASSWORD must be set as environment variables."
    return None


def build_session() -> requests.Session:
    session = requests.Session()
    session.verify = VERIFY_SSL
    session.headers.update({"Content-Type": "application/json"})
    return session


def login(session: requests.Session) -> None:
    resp = session.post(
        f"{UNIFI_HOST}/api/auth/login",
        data=json.dumps({"username": UNIFI_USERNAME, "password": UNIFI_PASSWORD}),
    )
    resp.raise_for_status()


def fetch_clients(session: requests.Session) -> Dict[str, dict]:
    resp = session.get(f"{UNIFI_HOST}/proxy/network/api/s/{UNIFI_SITE}/rest/user")
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return {c.get("mac", "").lower(): c for c in data if c.get("mac")}


def get_containers() -> Tuple[List[dict], Dict[str, dict]]:
    client = docker.from_env()
    containers = []
    index = {}
    for c in client.containers.list():
        networks = (c.attrs.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
        for net_name, net in networks.items():
            mac = net.get("MacAddress")
            ip = net.get("IPAddress")
            if not mac or not ip:
                continue
            entry = {
                "name": c.name,
                "network": net_name,
                "mac": mac.lower(),
                "ip": ip,
            }
            containers.append(entry)
            index[entry["mac"]] = entry
    return containers, index


def upsert_client(
    session: requests.Session, container: dict, existing: Optional[dict]
) -> str:
    mac = container["mac"].lower()
    network_id = (
        (existing or {}).get("network_id")
        or (existing or {}).get("network")
        or UNIFI_NETWORK_ID
    )

    if not network_id:
        raise ValueError(
            f"network_id is required to create/update {mac}. "
            "Set UNIFI_NETWORK_ID or ensure the client already has network_id."
        )

    desired = {
        "name": container["name"],
        "fixed_ip": container["ip"],
        "use_fixedip": True,
        "network_id": network_id,
    }

    if existing:
        payload = {**existing, **desired}
        resp = session.put(
            f"{UNIFI_HOST}/proxy/network/api/s/{UNIFI_SITE}/rest/user/{existing['_id']}",
            data=json.dumps(payload),
        )
        resp.raise_for_status()
        return f"Updated {mac} -> {container['name']} @ {container['ip']}"

    payload = {"mac": mac, **desired}
    resp = session.post(
        f"{UNIFI_HOST}/proxy/network/api/s/{UNIFI_SITE}/rest/user",
        data=json.dumps(payload),
    )
    resp.raise_for_status()
    return f"Created {mac} -> {container['name']} @ {container['ip']}"


@app.route("/api/status")
def api_status():
    cfg_error = ensure_configured()
    if cfg_error:
        return jsonify({"error": cfg_error}), 500

    containers, container_index = get_containers()

    session = build_session()
    try:
        login(session)
        clients = fetch_clients(session)
    except Exception as exc:
        return jsonify({"error": f"Unable to reach UniFi: {exc}"}), 502

    router_list = []
    for mac, data in clients.items():
        router_list.append(
            {
                "mac": mac,
                "name": data.get("name") or data.get("hostname") or "",
                "hostname": data.get("hostname") or "",
                "fixed_ip": data.get("fixed_ip") or "",
                "use_fixedip": data.get("use_fixedip", False),
            }
        )

    return jsonify(
        {
            "containers": containers,
            "router_clients": router_list,
            "configured": True,
            "verify_ssl": VERIFY_SSL,
            "unifi_host": UNIFI_HOST,
        }
    )


@app.route("/api/apply", methods=["POST"])
def api_apply():
    cfg_error = ensure_configured()
    if cfg_error:
        return jsonify({"error": cfg_error}), 500

    body = request.get_json(force=True, silent=True) or {}
    mac = (body.get("mac") or "").lower()
    if not mac:
        return jsonify({"error": "mac is required"}), 400

    containers, container_index = get_containers()
    container = container_index.get(mac)
    if not container:
        return jsonify({"error": f"No running container with MAC {mac}"}), 404

    session = build_session()
    try:
        login(session)
        clients = fetch_clients(session)
        existing = clients.get(mac)
        message = upsert_client(session, container, existing)
        return jsonify({"ok": True, "message": message})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/")
def index():
    return render_template_string(
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Unraid ↔ UniFi Mapper</title>
    <style>
      :root {
        font-family: "Segoe UI", sans-serif;
        background: #0f172a;
        color: #e2e8f0;
      }
      body { margin: 0; padding: 24px; }
      h1 { margin-top: 0; letter-spacing: 0.02em; }
      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
      .card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.3);
      }
      .card h2 { margin: 0 0 12px; font-size: 16px; letter-spacing: 0.02em; }
      .row {
        display: grid;
        grid-template-columns: 1.4fr 1fr 1fr;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid #1f2937;
        gap: 12px;
      }
      .row:last-child { border-bottom: none; }
      .label { color: #94a3b8; font-size: 12px; }
      .btn {
        padding: 6px 10px;
        border-radius: 8px;
        border: 1px solid #38bdf8;
        background: linear-gradient(120deg, #06b6d4, #3b82f6);
        color: #0b1224;
        font-weight: 600;
        cursor: pointer;
        transition: transform 80ms ease, box-shadow 120ms ease;
      }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
      .btn:not(:disabled):hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(59,130,246,0.35); }
      .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        background: #1e293b;
        color: #cbd5f5;
        font-size: 11px;
      }
      .status { margin: 12px 0; color: #cbd5e1; }
      .error { color: #fca5a5; }
      code { color: #7dd3fc; }
    </style>
  </head>
  <body>
    <h1>Unraid ↔ UniFi Docker Mapper</h1>
    <div class="status" id="status">Loading…</div>
    <div class="grid">
      <div class="card">
        <h2>Unraid Containers</h2>
        <div class="row label">
          <div>Name</div><div>MAC</div><div>IP</div>
        </div>
        <div id="unraid"></div>
      </div>
      <div class="card">
        <h2>UniFi Router Clients</h2>
        <div class="row label">
          <div>Name / Host</div><div>MAC</div><div>Fixed IP</div>
        </div>
        <div id="router"></div>
      </div>
    </div>

    <script>
      const statusEl = document.getElementById("status");
      const unraidEl = document.getElementById("unraid");
      const routerEl = document.getElementById("router");

      function rowTemplate(cols) {
        return `<div class="row">${cols.map(col => `<div>${col || ""}</div>`).join("")}</div>`;
      }

      async function loadData() {
        statusEl.textContent = "Loading…";
        try {
          const res = await fetch("/api/status");
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || res.statusText);

          renderColumns(data);
          statusEl.textContent = "Connected";
        } catch (err) {
          statusEl.innerHTML = `<span class="error">${err.message}</span>`;
        }
      }

      function renderColumns(data) {
        const containers = data.containers || [];
        const router = data.router_clients || [];
        const containerByMac = {};
        containers.forEach(c => containerByMac[c.mac] = c);

        unraidEl.innerHTML = containers.length
          ? containers.map(c => rowTemplate([
              `<strong>${c.name}</strong><div class="pill">${c.network}</div>`,
              `<code>${c.mac}</code>`,
              `<code>${c.ip}</code>`
            ])).join("")
          : '<div class="row"><div>No running containers found.</div></div>';

        routerEl.innerHTML = router.length
          ? router.map(r => {
              const match = containerByMac[r.mac];
              const disabled = !match;
              const title = disabled ? "No matching container MAC to apply" : "Apply name + fixed IP from Unraid container";
              return rowTemplate([
                `<strong>${r.name || "—"}</strong><div class="pill">${r.hostname || "host?"}</div>`,
                `<code>${r.mac}</code>`,
                `<div style="display:flex; gap:8px; align-items:center;">
                   <code>${r.fixed_ip || "—"}</code>
                   <button class="btn" ${disabled ? "disabled" : ""} title="${title}" onclick="apply('${r.mac}')">Approve</button>
                 </div>`
              ]);
            }).join("")
          : '<div class="row"><div>No router clients returned.</div></div>';
      }

      async function apply(mac) {
        statusEl.textContent = `Applying ${mac}…`;
        try {
          const res = await fetch("/api/apply", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({mac})
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || res.statusText);
          statusEl.textContent = data.message || "Updated.";
          await loadData();
        } catch (err) {
          statusEl.innerHTML = `<span class="error">${err.message}</span>`;
        }
      }

      loadData();
    </script>
  </body>
</html>
        """
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
