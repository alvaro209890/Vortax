import { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  auth,
  createUserWithEmailAndPassword,
  googleProvider,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
  updateProfile,
} from "../lib/firebase.js";
import { setAuthTokenProvider, setCachedAuthToken } from "../lib/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAuthTokenProvider(async (forceRefresh = false) => auth.currentUser?.getIdToken(forceRefresh) || "");
    const unsubscribe = onIdTokenChanged(auth, async (nextUser) => {
      setUser(nextUser);
      setCachedAuthToken(nextUser ? await nextUser.getIdToken() : "");
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const value = useMemo(() => ({
    user,
    loading,
    async getIdToken() {
      return auth.currentUser?.getIdToken() || "";
    },
    async loginWithEmail(email, password) {
      await signInWithEmailAndPassword(auth, email, password);
    },
    async registerWithEmail({ email, password, name }) {
      const credential = await createUserWithEmailAndPassword(auth, email, password);
      if (name?.trim()) {
        await updateProfile(credential.user, { displayName: name.trim() });
      }
    },
    async loginWithGoogle() {
      await signInWithPopup(auth, googleProvider);
    },
    async signOut() {
      await firebaseSignOut(auth);
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
