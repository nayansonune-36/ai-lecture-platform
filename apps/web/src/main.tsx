import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App.js";

// Register Service Worker for PWA capabilities (does not cache media)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      // SW registration error handled gracefully
      console.debug("ServiceWorker registration skipped or failed:", err);
    });
  });
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Failed to find the root element");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
