import { FormEvent, useState } from "react";
import { getToken, isAuthEnabled, setDevToken } from "../lib/auth";

export function DevTokenBar() {
  const [token, setToken] = useState(getToken());

  if (isAuthEnabled()) {
    return null;
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setDevToken(token);
  };

  return (
    <form onSubmit={submit} className="dev-token-bar">
      <input
        className="input"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder="admin:admin@example.com"
      />
      <button className="button button-secondary" type="submit">Set Token</button>
    </form>
  );
}
