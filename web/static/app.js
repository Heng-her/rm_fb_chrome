function openChrome(sessionId = null) {
  let customUrl =
    document.getElementById("custom_url").value || "https://m.facebook.com";
  let customProxy = document.getElementById("custom_proxy").value || null;
  let vpnLocation = document.getElementById("vpn_location").value || null;

  // If reopening an existing session, we don't need to send new custom values
  // unless the backend expects them to override.
  const payload = {
    session_id: sessionId,
    url: sessionId ? null : customUrl,
    proxy: sessionId ? null : customProxy,
    vpn_server: sessionId ? null : vpnLocation,
  };

  fetch("/open_chrome", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function createNewProfile() {
  let customProxy = document.getElementById("custom_proxy").value || null;
  let vpnLocation = document.getElementById("vpn_location").value || null;

  fetch("/create_profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      proxy: customProxy,
      vpn_server: vpnLocation,
    }),
  }).then(() => loadStatus());
}

function loadVpnLocations() {
  fetch("/vpn_locations")
    .then((r) => r.json())
    .then((locations) => {
      const select = document.getElementById("vpn_location");
      locations.forEach((loc) => {
        const opt = document.createElement("option");
        opt.value = loc.server;
        opt.textContent = loc.name;
        select.appendChild(opt);
      });
    });
}
loadVpnLocations();

function CloseChrom(SessionId = null) {
  fetch("/close_chrome", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: SessionId,
    }),
  });
}

function deleteProfile(sessionId) {
  if (
    !confirm(
      "Are you sure you want to delete this profile? All data will be lost.",
    )
  )
    return;

  fetch("/delete_profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
    }),
  }).then(() => loadStatus());
}

function loadStatus() {
  fetch("/status")
    .then((r) => r.json())
    .then((data) => {
      const tbody = document.getElementById("sessions");
      tbody.innerHTML = "";

      for (const id in data) {
        const s = data[id];

        let actionButton = "";
        if (s.status === "OPEN") {
          actionButton = `<button onclick="CloseChrom('${id}')">Close</button>`;
        } else {
          actionButton = `
                        <button onclick="openChrome('${id}')">Open</button>
                        <button onclick="deleteProfile('${id}')" style="color: red;">Delete</button>
                    `;
        }

        tbody.innerHTML += `
                    <tr>
                        <td>${id}</td>
                        <td>${s.status}</td>
                        <td>${s.vpn_server || "None"}</td>
                        <td>${s.ip || "Unknown"}</td>
                        <td>${s.timezone || "Unknown"}</td>
                        <td>${s.url}</td>
                        <td>${actionButton}</td>
                    </tr>
                `;
      }
    });
}

function loadCredentials() {
  fetch("/credentials")
    .then((r) => r.json())
    .then((data) => {
      if (data.username)
        document.getElementById("surf_username").value = data.username;
      if (data.password)
        document.getElementById("surf_password").value = data.password;
    });
}

function saveCredentials() {
  let u = document.getElementById("surf_username").value;
  let p = document.getElementById("surf_password").value;

  fetch("/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u, password: p }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        let statusEl = document.getElementById("cred_status");
        statusEl.style.display = "inline";
        setTimeout(() => {
          statusEl.style.display = "none";
        }, 2000);
      }
    });
}

setInterval(loadStatus, 2000);
loadStatus();
loadCredentials();
