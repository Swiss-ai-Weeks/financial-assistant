const field = document.getElementById("desk");

chrome.storage.sync.get("desk").then(({ desk }) => {
  field.value = desk ?? "";
});

document.getElementById("save").addEventListener("click", async () => {
  const desk = field.value.trim();

  if (desk) await chrome.storage.sync.set({ desk });
  else await chrome.storage.sync.remove("desk");

  document.getElementById("saved").textContent = " Saved.";
});
