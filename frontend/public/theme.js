// Paint the right theme before React loads: no flash between light and dark.
// A separate file, not inline, so the app's strict CSP (script-src 'self') allows it.
try {
  var m = localStorage.getItem("spark.theme");
  var dark = m === "dark" || (m !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  if (dark) document.documentElement.classList.add("dark");
} catch (e) {}
