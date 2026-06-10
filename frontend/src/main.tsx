import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import { frontendSettings } from "./config";
import "./skins/dawn-table.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: frontendSettings.queryStaleTimeMs,
      retry: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
