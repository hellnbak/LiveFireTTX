(() => {
  const fileInput = document.getElementById("pack-file");
  const jsonInput = document.getElementById("pack-json");
  if (!fileInput || !jsonInput) return;
  fileInput.addEventListener("change", async () => {
    const [file] = fileInput.files;
    if (!file) return;
    if (file.size > 262144) {
      fileInput.setCustomValidity("Scenario pack files must be 256 KB or smaller.");
      fileInput.reportValidity();
      return;
    }
    fileInput.setCustomValidity("");
    jsonInput.value = await file.text();
  });
})();
