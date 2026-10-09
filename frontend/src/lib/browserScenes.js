// Cenas do navegador: capturas reais (screen_frame), leituras HTTP e buscas
// (browser_view) e telas protegidas (screen_frame_blocked). Nada aqui gera imagem.

export function isBrowserScene(event) {
  if (event?.type === "browser_view" || event?.type === "screen_frame_blocked") return true;
  return event?.type === "screen_frame" && Boolean(event.payload?.image_base64)
    && !["about:blank", "chrome://newtab/"].includes(event.payload?.url);
}

// Origem da cena, para a interface nunca apresentar leitura HTTP como captura de tela.
export function sceneSource(event) {
  const payload = event?.payload || {};
  if (event?.type === "screen_frame_blocked") return "blocked";
  if (event?.type === "screen_frame") return "capture";
  if (payload.kind === "search") return payload.via === "cache" ? "cache" : "search";
  return "http";
}

export const SCENE_SOURCE_LABELS = {
  blocked: "Tela protegida",
  cache: "Fontes já reunidas na conversa",
  capture: "Captura do navegador",
  http: "Leitura HTTP da página",
  search: "Resultados de busca",
};

export function browserScene(event, frameIndex, eventIndex = frameIndex) {
  const p = event.payload || {};
  const blocked = event.type === "screen_frame_blocked";
  const createdAt = Date.parse(p.captured_at || event.created_at) || 0;
  return {
    blocked,
    callId: p.call_id || null,
    capturedAt: createdAt,
    createdAt,
    cursor: blocked ? null : p.cursor,
    eventIndex,
    frameIndex,
    image: blocked ? null : p.image_base64,
    label: p.caption || p.title || "Navegador",
    mode: "browser",
    source: sceneSource(event),
    title: p.title || "",
    trigger: p.trigger || "",
    url: p.url || "",
    using: "Navegador",
    view: event.type === "browser_view" ? p : null,
    viewport: p.viewport,
  };
}

// Posição do ponteiro em porcentagem da área da captura. A captura é exibida dentro de
// um palco com a mesma proporção do viewport capturado, então não há margens a descontar.
export function cursorPosition(cursor, viewport) {
  if (!cursor || !(viewport?.width > 0) || !(viewport?.height > 0)) return null;
  if (!Number.isFinite(cursor.x) || !Number.isFinite(cursor.y)) return null;
  return { x: Math.max(0, Math.min(98, cursor.x / viewport.width * 100)),
    y: Math.max(0, Math.min(98, cursor.y / viewport.height * 100)) };
}

// Retângulo ocupado por uma imagem com object-fit: contain dentro de uma caixa.
// Usado para conferir que o palco proporcional coincide com a imagem visível.
export function containRect(boxWidth, boxHeight, imageWidth, imageHeight) {
  if (!(boxWidth > 0 && boxHeight > 0 && imageWidth > 0 && imageHeight > 0)) return null;
  const scale = Math.min(boxWidth / imageWidth, boxHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return { height, left: (boxWidth - width) / 2, scale, top: (boxHeight - height) / 2, width };
}

// Ponteiro em pixels da caixa, descontando as faixas vazias (letterbox) do contain.
export function pointerInBox(cursor, viewport, boxWidth, boxHeight) {
  if (!cursor || !(viewport?.width > 0) || !(viewport?.height > 0)) return null;
  if (!Number.isFinite(cursor.x) || !Number.isFinite(cursor.y)) return null;
  const rect = containRect(boxWidth, boxHeight, viewport.width, viewport.height);
  if (!rect) return null;
  return { x: rect.left + cursor.x * rect.scale, y: rect.top + cursor.y * rect.scale };
}
