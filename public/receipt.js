const statusEl = document.getElementById("status");
const eventsEl = document.getElementById("events");

const params = new URLSearchParams(window.location.search);
const receiptId = params.get("id");

if (!receiptId) {
  statusEl.textContent = "Missing receipt id. Use receipt.html?id=...";
} else {
  loadReceipt(receiptId);
}

async function loadReceipt(id) {
  statusEl.textContent = "Loading...";

  try {
    const response = await fetch(`/api/receipts/${id}`);
    const payload = await response.json();

    if (!response.ok) {
      statusEl.textContent = payload.error || "Receipt not found";
      return;
    }

    statusEl.textContent = `Events for ${payload.imageId}`;
    renderEvents(payload.events || []);
  } catch (err) {
    statusEl.textContent = "Failed to load receipt.";
  }
}

function renderEvents(events) {
  eventsEl.innerHTML = "";

  if (events.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "No events yet.";
    row.appendChild(cell);
    eventsEl.appendChild(row);
    return;
  }

  for (const event of events) {
    const row = document.createElement("tr");
    row.appendChild(textCell(event.timestamp));
    row.appendChild(textCell(event.ip));
    row.appendChild(textCell(event.userAgent));
    row.appendChild(textCell(event.referrer || ""));
    eventsEl.appendChild(row);
  }
}

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value || "";
  return cell;
}
