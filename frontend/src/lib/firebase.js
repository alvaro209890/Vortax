import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported } from "firebase/analytics";
import {
  createUserWithEmailAndPassword,
  getAuth,
  GoogleAuthProvider,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyBHCGu4kaWvmoyRZDoxufFThdxGZWoDG9A",
  authDomain: "notazap-2520f.firebaseapp.com",
  projectId: "notazap-2520f",
  storageBucket: "notazap-2520f.firebasestorage.app",
  messagingSenderId: "686340808252",
  appId: "1:686340808252:web:f4da6b7f8e5c1084202d39",
  measurementId: "G-DLC56LF47K",
};

export const firebaseApp = initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
export const googleProvider = new GoogleAuthProvider();

isSupported()
  .then((supported) => {
    if (supported) getAnalytics(firebaseApp);
  })
  .catch(() => {});

export {
  createUserWithEmailAndPassword,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
};
