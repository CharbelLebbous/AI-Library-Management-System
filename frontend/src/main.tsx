import React from "react";
import ReactDOM from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./styles.css";
import { getAuth0Config, isAuthEnabled } from "./lib/auth";

const queryClient = new QueryClient();
const auth0 = getAuth0Config();

const app = (
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);

if (isAuthEnabled()) {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <Auth0Provider
      domain={auth0.domain}
      clientId={auth0.clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: auth0.audience || undefined,
        scope: "openid profile email"
      }}
      cacheLocation="localstorage"
      useRefreshTokens
    >
      {app}
    </Auth0Provider>
  );
} else {
  ReactDOM.createRoot(document.getElementById("root")!).render(app);
}
