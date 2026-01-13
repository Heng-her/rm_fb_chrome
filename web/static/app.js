function openChrome(sessionId = null) {
    fetch("/open_chrome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: sessionId
        })
    });
}
function CloseChrom(SessionId = null) {
    fetch("/close_chrome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: SessionId
        })
    })
}

function loadStatus() {
    fetch("/status")
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById("sessions");
            tbody.innerHTML = "";

            for (const id in data) {
                const s = data[id];

                tbody.innerHTML += `
                    <tr>
                        <td>${id}</td>
                        <td>${s.status}</td>
                        <td>${s.url}</td>
                        <td>
                            <button onclick="openChrome('${id}')">Open</button>
                            <button onclick="CloseChrom('${id}')">Close</button>
                        </td>
                    </tr>
                `;
            }
        });
}

setInterval(loadStatus, 2000);
loadStatus();