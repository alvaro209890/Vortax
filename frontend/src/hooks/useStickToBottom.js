import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const THRESHOLD = 72;

/**
 * Acompanha o fim de uma área rolável só enquanto a pessoa está no fim dela.
 * Se ela subir para ler algo anterior, as atualizações não a arrastam; um contador de
 * novidades e scrollToBottom() permitem voltar a acompanhar.
 */
export function useStickToBottom(changeKey, { resetKey } = {}) {
  const ref = useRef(null);
  const stuckRef = useRef(true);
  const [stuck, setStuck] = useState(true);
  const [unseen, setUnseen] = useState(0);
  const lastKeyRef = useRef(changeKey);

  const onScroll = useCallback(() => {
    const node = ref.current;
    if (!node) return;
    const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight <= THRESHOLD;
    if (atBottom !== stuckRef.current) {
      stuckRef.current = atBottom;
      setStuck(atBottom);
    }
    if (atBottom) setUnseen(0);
  }, []);

  const scrollToBottom = useCallback((behavior = "smooth") => {
    const node = ref.current;
    if (!node) return;
    stuckRef.current = true;
    setStuck(true);
    setUnseen(0);
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    node.scrollTo({ top: node.scrollHeight, behavior: reduced ? "auto" : behavior });
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  }, [onScroll]);

  // Ao trocar de conversa/sessão, começa pelo fim.
  useLayoutEffect(() => {
    stuckRef.current = true;
    setStuck(true);
    setUnseen(0);
    const node = ref.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [resetKey]);

  useLayoutEffect(() => {
    if (lastKeyRef.current === changeKey) return;
    lastKeyRef.current = changeKey;
    const node = ref.current;
    if (!node) return;
    if (stuckRef.current) {
      node.scrollTop = node.scrollHeight;
    } else {
      setUnseen((count) => count + 1);
    }
  }, [changeKey]);

  // Conteúdo que cresce sem mudar a chave (imagens, markdown) também mantém o fim.
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const inner = node.firstElementChild;
    if (!inner) return undefined;
    const observer = new ResizeObserver(() => {
      if (stuckRef.current) node.scrollTop = node.scrollHeight;
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

  return { ref, scrollToBottom, stuck, unseen };
}
