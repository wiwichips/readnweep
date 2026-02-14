const form = document.getElementById("upload-form");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const fileInput = document.getElementById("file-input");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Uploading...";
  resultEl.textContent = "";

  if (!fileInput.files || fileInput.files.length === 0) {
    statusEl.textContent = "Pick a file first.";
    return;
  }

  const data = new FormData();
  data.append("file", fileInput.files[0]);

  try {
    const response = await fetch("/api/images", {
      method: "POST",
      body: data,
    });

    const payload = await response.json();
    if (!response.ok) {
      statusEl.textContent = payload.error || "Upload failed";
      return;
    }

    statusEl.textContent = "Uploaded.";

    resultEl.innerHTML = `
      <p>Image URL: <a href="${payload.imageUrl}" target="_blank">${payload.imageUrl}</a></p>
      <p>Receipt URL: <a href="${payload.receiptUrl}" target="_blank">${payload.receiptUrl}</a></p>
      <p>Receipt ID: ${payload.receiptId}</p>
    `;
  } catch (err) {
    statusEl.textContent = "Upload failed.";
  }
});
