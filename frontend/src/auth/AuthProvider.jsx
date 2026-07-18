import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { setAuthTokenProvider, setCachedAuthToken } from "../lib/api.js";

const AuthContext = createContext(null);

// Usuário local fixo — sem Firebase
const LOCAL_USER = {
  uid: "local-dev-user",
  email: "vortax@local.host",
  displayName: "Vortax",
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(LOCAL_USER);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Token sempre vazio — backend aceita sem auth (ALLOW_NO_AUTH=true)
    setAuthTokenProvider(async () => "");
    setCachedAuthToken("");
    setUser(LOCAL_USER);
  }, []);

  const value = useMemo(() => ({
    user,
    loading,
    async getIdToken() {
      return "";
    },
    async loginWithEmail() {},
    async registerWithEmail() {},
    async loginWithGoogle() {},
    async signOut() {
      // Não desconecta — mantém o usuário local
      setCachedAuthToken("");
    },
  }), [loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider");
  }
  return value;
}
