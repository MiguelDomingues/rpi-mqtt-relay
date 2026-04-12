
async function fetchStatus() {
    const mqttList = document.getElementById('mqtt-list');
    const lcdLinesDiv = document.getElementById('lcd-lines');
    const gpioList = document.getElementById('gpio-list');
    const mqttOutList = document.getElementById('mqttout-list');

    // Show loading only if empty and not yet updated
    if (!mqttList.hasChildNodes() || (mqttList.children.length === 1 && mqttList.children[0].textContent === 'Loading...')) mqttList.innerHTML = '<li>Loading...</li>';
    if (!lcdLinesDiv.hasChildNodes()) lcdLinesDiv.innerHTML = 'Loading...';
    if (!gpioList.hasChildNodes() || (gpioList.children.length === 1 && gpioList.children[0].textContent === 'Loading...')) gpioList.innerHTML = '<li>Loading...</li>';
    if (!mqttOutList.hasChildNodes() || (mqttOutList.children.length === 1 && mqttOutList.children[0].textContent === 'Loading...')) mqttOutList.innerHTML = '<li>Loading...</li>';

    try {
        const res = await fetch('/status');
        if (!res.ok) throw new Error('Failed to fetch status');
        const data = await res.json();

        // --- MQTT Topics ---
        const mqttInputs = data.inputs?.mqtt || {};
        updateList(mqttList, mqttInputs, 'No MQTT topics');

        // --- LCD Lines ---
        const lcdLines = data.lcd || [];
        updateLcdLines(lcdLinesDiv, lcdLines);

        // --- GPIO Outputs ---
        const gpioOutputs = data.outputs?.gpio || {};
        updateList(gpioList, gpioOutputs, 'No GPIO outputs');

        // --- MQTT Outputs ---
        const mqttOutputs = data.outputs?.mqtt || {};
        updateList(mqttOutList, mqttOutputs, 'No MQTT outputs');

    } catch (e) {
        updateError(mqttList, e);
        updateError(lcdLinesDiv, e, true);
        updateError(gpioList, e);
        updateError(mqttOutList, e);
    }
}

function updateList(listElem, dataObj, emptyMsg) {
    // Remove 'Loading...' if present
    if (
        listElem.children.length === 1 &&
        listElem.children[0].textContent.trim().toLowerCase() === 'loading...'
    ) {
        listElem.innerHTML = '';
    }
    const keys = Object.keys(dataObj);
    if (keys.length === 0) {
        listElem.innerHTML = `<li>${emptyMsg}</li>`;
        return;
    }
    // Build a map of current <li> by key
    const existing = {};
    Array.from(listElem.children).forEach(li => {
        const key = li.getAttribute('data-key');
        if (key) existing[key] = li;
    });
    // Add/update
    keys.forEach(key => {
        const value = dataObj[key];
        let li = existing[key];
        if (!li) {
            li = document.createElement('li');
            li.setAttribute('data-key', key);
            listElem.appendChild(li);
        }
        // If value is an object with value/unit, show both
        if (value && typeof value === 'object' && 'value' in value) {
            let unit = value.unit ? ` <span style="color:#888;font-size:0.95em">${value.unit}</span>` : '';
            li.innerHTML = `<b>${key}</b>: <span>${value.value}</span>${unit}`;
        } else {
            li.innerHTML = `<b>${key}</b>: <span>${value}</span>`;
        }
        delete existing[key];
    });
    // Remove any <li> not in new data
    Object.values(existing).forEach(li => li.remove());
}

function updateLcdLines(container, lines) {
    // Only update changed lines
    if (lines.length === 0) {
        container.innerHTML = '<em>No LCD lines</em>';
        return;
    }
    // If the number of lines changed, rebuild
    if (container.children.length !== lines.length) {
        container.innerHTML = '';
        lines.forEach((line, i) => {
            const span = document.createElement('span');
            span.className = 'lcd-line';
            span.textContent = line;
            container.appendChild(span);
        });
    } else {
        // Update only changed lines
        Array.from(container.children).forEach((span, i) => {
            if (span.textContent !== lines[i]) {
                span.textContent = lines[i];
            }
        });
    }
}

function updateError(elem, e, isLcd) {
    if (isLcd) {
        elem.innerHTML = `<span style='color:red'>Error: ${e.message}</span>`;
    } else {
        elem.innerHTML = `<li style='color:red'>Error: ${e.message}</li>`;
    }
}

let autoRefresh = true;
let refreshInterval = 5000; // 5 seconds
let refreshTimer = null;

function setAutoRefresh(enabled) {
    autoRefresh = enabled;
    if (autoRefresh) {
        fetchStatus();
        refreshTimer = setInterval(fetchStatus, refreshInterval);
    } else {
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Set up auto-refresh toggle
    const toggle = document.getElementById('autorefresh-toggle');
    if (toggle) {
        toggle.checked = true;
        toggle.addEventListener('change', (e) => {
            setAutoRefresh(e.target.checked);
        });
    }
    setAutoRefresh(true);
});
