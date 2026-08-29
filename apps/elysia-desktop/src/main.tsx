import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import App from "./App";
import QuickInvokeWindow from "./QuickInvokeWindow";
import "./desktop.css";

const rootElement = document.querySelector<HTMLDivElement>("#app");

if (!rootElement) {
  throw new Error("Elysia desktop shell root #app was not found.");
}

const appRoot = rootElement;

function readWindowQueryParam(): string | null {
  try {
    return new URLSearchParams(window.location.search).get("window");
  } catch {
    return null;
  }
}

async function resolveWindowLabel(): Promise<string> {
  const queryLabel = readWindowQueryParam();
  if (queryLabel?.trim()) {
    return queryLabel.trim();
  }

  try {
    const currentWindow = getCurrentWebviewWindow();
    const label = currentWindow?.label;

    if (typeof label === "string" && label.trim()) {
      return label.trim();
    }
  } catch {
    // Fall through to main-window default.
  }

  return "main";
}

function renderRoot(element: React.ReactNode) {
  ReactDOM.createRoot(appRoot).render(
    <React.StrictMode>{element}</React.StrictMode>
  );
}

async function bootstrap() {
  const windowLabel = await resolveWindowLabel();

  if (windowLabel === "quick_invoke") {
    renderRoot(<QuickInvokeWindow />);
    return;
  }

  renderRoot(<App />);
}

void bootstrap();
