export function isBrowserScene(event) {
  if (event?.type === "browser_view" || event?.type === "screen_frame_blocked") return true;
  return event?.type === "screen_frame" && Boolean(event.payload?.image_base64)
    && !["about:blank", "chrome://newtab/"].includes(event.payload?.url);
}

export function browserScene(event, frameIndex, eventIndex = frameIndex) {
  const p = event.payload || {};
  const blocked = event.type === "screen_frame_blocked";
  return {
    createdAt: Date.parse(event.created_at) || 0, eventIndex, frameIndex,
    image: blocked ? null : p.image_base64, cursor: p.cursor, viewport: p.viewport,
    view: event.type === "browser_view" ? p : null, blocked,
    label: p.caption || p.title || "Navegador", mode: "browser",
    title: p.title || "", url: p.url || "", using: "Navegador",
  };
}

export function cursorPosition(cursor, viewport) {
  if (!cursor || !(viewport?.width > 0) || !(viewport?.height > 0)) return null;
  if (!Number.isFinite(cursor.x) || !Number.isFinite(cursor.y)) return null;
  return { x: Math.max(0, Math.min(98, cursor.x / viewport.width * 100)),
    y: Math.max(0, Math.min(98, cursor.y / viewport.height * 100)) };
}
