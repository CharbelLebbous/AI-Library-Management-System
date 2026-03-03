const authEnabled = import.meta.env.VITE_AUTH0_ENABLED === "true";

const authDomain = (import.meta.env.VITE_AUTH0_DOMAIN ?? "").trim();
const authClientId = (import.meta.env.VITE_AUTH0_CLIENT_ID ?? "").trim();
const authAudience = (import.meta.env.VITE_AUTH0_AUDIENCE ?? "").trim();

export function getToken(): string {
  if (authEnabled) {
    return localStorage.getItem("aspire_auth_token") ?? "";
  }
  return localStorage.getItem("aspire_dev_token") ?? "admin:admin@example.com";
}

export function setDevToken(token: string): void {
  localStorage.setItem("aspire_dev_token", token);
}

export function isAuthEnabled(): boolean {
  return authEnabled && !!authDomain && !!authClientId;
}

export function getAuth0Config() {
  return {
    domain: authDomain,
    clientId: authClientId,
    audience: authAudience
  };
}
