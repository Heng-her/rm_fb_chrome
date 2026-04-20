function openChrome(sessionId = null) {
    const customUrl = document.getElementById("custom_url").value || "https://m.facebook.com";
    const customProxy = document.getElementById("custom_proxy").value || null;

    fetch("/open_chrome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: sessionId,
            url: customUrl,
            proxy: customProxy
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

                const actionButton = s.status === "OPEN" 
                    ? `<button onclick="CloseChrom('${id}')">Close</button>`
                    : `<button onclick="openChrome('${id}')">Open</button>`;

                tbody.innerHTML += `
                    <tr>
                        <td>${id}</td>
                        <td>${s.status}</td>
                        <td>${s.ip || 'Unknown'}</td>
                        <td>${s.timezone || 'Unknown'}</td>
                        <td>${s.url}</td>
                        <td>${actionButton}</td>
                    </tr>
                `;
            }
        });
}

setInterval(loadStatus, 2000);
loadStatus();