import { useAuth0 } from "@auth0/auth0-react";

export function AuthControls() {
  const { isLoading, isAuthenticated, loginWithRedirect, logout, user, error } = useAuth0();

  if (isLoading) {
    return <p className="meta-text">Initializing SSO session...</p>;
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-stack">
        <div className="auth-row">
          <span className="meta-text">SSO Mode: You are not signed in.</span>
          <button className="button button-primary" onClick={() => loginWithRedirect()}>
            Sign In with SSO
          </button>
        </div>
        {error && (
          <div className="alert alert-error">
            SSO error: {error.message}
          </div>
        )}
        <div className="meta-text">
          Origin: {window.location.origin}
        </div>
      </div>
    );
  }

  return (
    <div className="auth-row">
      <span>
        Signed in as <strong>{user?.email ?? user?.name ?? "user"}</strong>
      </span>
      <button
        className="button button-secondary"
        onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
      >
        Sign Out
      </button>
    </div>
  );
}
