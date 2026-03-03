import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";

import { setAuthTokenResolver } from "../api";

export function Auth0TokenBridge() {
  const { isAuthenticated, getAccessTokenSilently } = useAuth0();

  useEffect(() => {
    setAuthTokenResolver(async () => {
      if (!isAuthenticated) {
        return "";
      }
      return await getAccessTokenSilently();
    });

    return () => {
      setAuthTokenResolver(null);
    };
  }, [getAccessTokenSilently, isAuthenticated]);

  return null;
}
