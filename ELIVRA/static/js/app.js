document.addEventListener("DOMContentLoaded", () => {
    loadDashboardMetrics();
    loadVoters();
    loadAuditLogs();

    // Attach form handler for new voter registration
    const regForm = document.getElementById("registerVoterForm");
    if (regForm) {
        regForm.addEventListener("submit", handleVoterRegistration);
    }
});

// 1. Fetch Summary Statistics
async function loadDashboardMetrics() {
    try {
        const res = await fetch('/api/dashboard');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById("stat-total-voters").textContent = data.total_voters;
        document.getElementById("stat-verified-voters").textContent = data.verified_voters;
        document.getElementById("stat-open-anomalies").textContent = data.open_anomalies;
        document.getElementById("stat-integrity-alerts").textContent = data.integrity_alerts;
    } catch (e) {
        console.error("Metrics load failed:", e);
    }
}

// 2. Load & Render Voter Records
async function loadVoters() {
    try {
        const res = await fetch('/api/voters');
        if (!res.ok) return;
        const voters = await res.json();
        
        const tbody = document.getElementById("voterTableBody");
        tbody.innerHTML = "";

        if (voters.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center">No voter records registered yet.</td></tr>`;
            return;
        }

        voters.forEach(v => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${v.registration_id}</strong></td>
                <td>${v.full_name}</td>
                <td><code>${v.national_id}</code></td>
                <td>${v.county}, ${v.constituency}</td>
                <td><span class="status-pill status-${v.verification_status.toLowerCase()}">${v.verification_status}</span></td>
                <td>
                    <button class="btn-verify-hash" onclick="verifyIntegrity(${v.id}, this)">
                        Verify Hash
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Voters load failed:", e);
    }
}

// 3. Register New Voter Handler
async function handleVoterRegistration(e) {
    e.preventDefault();

    const payload = {
        registration_id: document.getElementById("regId").value,
        full_name: document.getElementById("fullName").value,
        national_id: document.getElementById("nationalId").value,
        date_of_birth: document.getElementById("dob").value,
        county: document.getElementById("county").value,
        constituency: document.getElementById("constituency").value,
        ward: document.getElementById("ward").value
    };

    try {
        const res = await fetch('/api/voters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            document.getElementById("registerVoterForm").reset();
            loadDashboardMetrics();
            loadVoters();
            loadAuditLogs();
        } else {
            alert("Error registering voter. Check for duplicate IDs.");
        }
    } catch (err) {
        console.error("Registration error:", err);
    }
}

// 4. Run Hash Verification on Demand
async function verifyIntegrity(voterId, buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "Checking...";

    try {
        const res = await fetch(`/api/integrity/check/${voterId}`, { method: 'POST' });
        const data = await res.json();

        if (data.match) {
            buttonEl.textContent = "Valid ✓";
            buttonEl.className = "btn-verify-hash match-success";
        } else {
            buttonEl.textContent = "Violation ❌";
            buttonEl.className = "btn-verify-hash match-failed";
        }
        loadDashboardMetrics();
        loadAuditLogs();
    } catch (e) {
        buttonEl.textContent = "Error ⚠️";
    }
}

// 5. Load Real-Time Audit Stream
async function loadAuditLogs() {
    try {
        const res = await fetch('/api/audit-logs');
        if (!res.ok) return;
        const logs = await res.json();

        const container = document.getElementById("auditLogStream");
        container.innerHTML = "";

        logs.slice(0, 15).forEach(l => {
            const div = document.createElement("div");
            div.className = "log-entry";
            div.innerHTML = `
                <span class="log-time">${l.created_at.split(' ')[1]}</span>
                <span class="log-action">[${l.action}]</span>
                <span class="log-desc">${l.description}</span>
            `;
            container.appendChild(div);
        });
    } catch (e) {
        console.error("Audit log error:", e);
    }
}


// ==========================================
// 6. 3D AMBIENT MODAL CONTROLLER & DATA FETCHING
// ==========================================

const statModalData = {
    totalVoters: {
        title: "Total Registered Voters",
        subtitle: "Complete registered citizen list in the ELIVRA database",
        glowClass: "glow-purple",
        iconEmoji: "👥",
        headers: ["Reg ID", "Full Name", "National ID", "County", "Status"],
        rows: [
            ["REG-10928", "Shelton Muigai", "38291029", "Nairobi", "<span class='status-pill status-verified'>Verified</span>"],
            ["REG-10929", "Alice Johnson", "49201849", "Kiambu", "<span class='status-pill status-verified'>Verified</span>"],
            ["REG-10930", "David Smith", "10928340", "Mombasa", "<span class='status-pill status-pending'>Flagged</span>"],
            ["REG-10931", "Shelton Muigai", "38291029", "Nairobi", "<span class='status-pill status-pending'>Duplicate</span>"]
        ]
    },
    verifiedVoters: {
        title: "Verified Clean Records",
        subtitle: "Voters passing all demographic & SHA-256 cryptographic checks",
        glowClass: "glow-green",
        iconEmoji: "✅",
        headers: ["Reg ID", "Full Name", "National ID", "SHA-256 Hash Status"],
        rows: [
            ["REG-10928", "Shelton Muigai", "38291029", "<span class='status-pill status-verified'>Hash Match (Verified)</span>"],
            ["REG-10929", "Alice Johnson", "49201849", "<span class='status-pill status-verified'>Hash Match (Verified)</span>"]
        ]
    },
    openAnomalies: {
        title: "Open Anomaly Queue",
        subtitle: "Flagged voter records requiring manual investigation & triage",
        glowClass: "glow-amber",
        iconEmoji: "⚠️",
        headers: ["Reg ID", "Name / ID", "Anomaly Flag", "Severity"],
        rows: [
            ["REG-10930", "David Smith (10928340)", "Underage Registration", "<span style='color:#fbbf24; font-weight:600;'>Medium</span>"],
            ["REG-10931", "Shelton Muigai (38291029)", "Duplicate National ID", "<span style='color:#f87171; font-weight:600;'>High</span>"]
        ]
    },
    integrityAlerts: {
        title: "Cryptographic Integrity Alerts",
        subtitle: "SHA-256 hash mismatch - Potential out-of-band database tampering",
        glowClass: "glow-blue",
        iconEmoji: "🛡️",
        headers: ["Reg ID", "Target Field", "Recorded Audit Hash", "Live DB Hash Status"],
        rows: [
            ["REG-10930", "Full Name", "a8f5f167...", "<span style='color:#f87171; font-weight:600;'>HASH MISMATCH</span>"]
        ]
    }
};

function openStatModal(type) {
    const data = statModalData[type];
    if (!data) return;

    const modalOverlay = document.getElementById('statModalOverlay');
    const modalBox = document.getElementById('statModal3D');
    
    document.getElementById('modalTitle').innerText = data.title;
    document.getElementById('modalSubtitle').innerText = data.subtitle;
    document.getElementById('modalIconContainer').innerText = data.iconEmoji;

    modalBox.className = 'modal-3d ' + data.glowClass;

    const thead = document.getElementById('modalTableHead');
    thead.innerHTML = data.headers.map(h => `<th>${h}</th>`).join('');

    const tbody = document.getElementById('modalTableBody');
    tbody.innerHTML = data.rows.map(row => 
        `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
    ).join('');

    modalOverlay.classList.add('active');
}

function closeStatModal(eventOrForce) {
    const modalOverlay = document.getElementById('statModalOverlay');
    if (eventOrForce === true || (eventOrForce.target && eventOrForce.target.id === 'statModalOverlay')) {
        modalOverlay.classList.remove('active');
    }
}