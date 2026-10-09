import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { buildActivity, groupActions, turnHeadline, turnResults } from "../src/lib/activity.js";

// Fixtures: eventos reais gravados numa execução de QA isolada (ver _fixture em cada arquivo).
const site = JSON.parse(readFileSync(new URL("./fixtures/legacy-site-task.json", import.meta.url)));
const browser = JSON.parse(readFileSync(new URL("./fixtures/legacy-browser-task.json", import.meta.url)));

const ev = (type, payload = {}, extra = {}) => ({ type, payload, created_at: "2026-10-09T12:00:00Z", ...extra });

test("legacy site task: actions get human titles and real targets", () => {
  const { turns } = buildActivity(site.events, { agentStatus: "done" });
  const actions = turns.at(-1).actions;
  assert.deepEqual(actions.map((action) => action.title), [
    "Criou index.html",
    "Criou style.css",
    "Criou script.js",
    "Leu index.html",
    "Editou index.html",
    "Validação aprovada",
    "Executou comando",
    "Capturou a tela",
  ]);
  assert.equal(actions[0].target.value, "index.html");
  assert.equal(actions[6].target.value, "ls -la");
  assert.ok(actions[6].output.some((line) => line.text.includes("index.html")), "terminal output comes from shell_stdout");
  assert.ok(actions.every((action) => action.status === "done"));
  assert.equal(actions[7].frames.length, 1, "screenshot frame belongs to the screenshot action");
});

test("legacy browser task: go_back exception closes the call as failed, not running", () => {
  const { turns } = buildActivity(browser.events, { agentStatus: "done" });
  const goBack = turns.at(-1).actions.find((action) => action.tool === "browser_go_back");
  assert.equal(goBack.status, "failed");
  assert.match(goBack.error, /Timeout/);
  assert.equal(goBack.title, "Não conseguiu voltar à página anterior");
});

test("browser frames are attached to the action that produced them", () => {
  const { turns, frames } = buildActivity(browser.events, { agentStatus: "done" });
  const actions = turns.at(-1).actions;
  const type = actions.find((action) => action.tool === "browser_type");
  assert.ok(type.frames.length >= 1);
  const blocked = actions.find((action) => action.tool === "browser_click_text" && action.params.text === "Área do cliente");
  assert.ok(blocked.frames.some((index) => browser.events[index].type === "screen_frame_blocked"));
  assert.ok(frames.every((frame) => frame.actionId), "every capture has an owner action");
});

test("a running tool stops spinning once the task stops, fails or finishes", () => {
  const events = [
    ev("user_message", { content: "rode" }),
    ev("tool_call", { name: "shell_run", params: { command: "python3 longo.py" }, call_id: "tc_1" }),
    ev("shell_stdout", { line: "lote 1", call_id: "tc_1" }),
  ];
  assert.equal(buildActivity(events, { agentStatus: "running" }).turns[0].actions[0].status, "running");
  assert.equal(buildActivity(events, { agentStatus: "stopped" }).turns[0].actions[0].status, "interrupted");
  assert.equal(buildActivity(events, { agentStatus: "error" }).turns[0].actions[0].status, "interrupted");
  assert.equal(buildActivity(events, { agentStatus: "done" }).turns[0].actions[0].status, "unknown");
  assert.equal(buildActivity(events, { agentStatus: "paused" }).turns[0].actions[0].status, "paused");
});

test("an earlier sequential tool does not keep spinning while the task continues", () => {
  const events = [
    ev("user_message", { content: "x" }),
    ev("tool_call", { name: "browser_navigate", params: { url: "https://a.test" } }),
    ev("tool_call", { name: "browser_click_text", params: { text: "Entrar" } }),
  ];
  const [first, second] = buildActivity(events, { agentStatus: "running" }).turns[0].actions;
  assert.equal(first.status, "unknown");
  assert.equal(second.status, "running");
});

test("parallel calls pair by call_id even when results arrive out of order", () => {
  const events = [
    ev("user_message", { content: "pesquise" }),
    ev("tool_call", { name: "web_fetch", params: { url: "https://a.test/1" }, call_id: "tc_a" }),
    ev("tool_call", { name: "web_fetch", params: { url: "https://b.test/2" }, call_id: "tc_b" }),
    ev("tool_result", { name: "web_fetch", result: { success: true, url: "https://b.test/2", title: "B" }, call_id: "tc_b" }),
  ];
  const [a, b] = buildActivity(events, { agentStatus: "running" }).turns[0].actions;
  assert.equal(a.status, "running");
  assert.equal(b.status, "done");
  assert.equal(b.title, "Leu B");
});

test("waiting for the user is its own state", () => {
  const events = [
    ev("user_message", { content: "publique" }),
    ev("confirmation_request", { message: "Posso publicar?" }),
    ev("agent_status", { status: "paused", label: "Aguardando usuário" }),
  ];
  const turn = buildActivity(events, { agentStatus: "paused", pendingConfirmation: { message: "Posso publicar?" } }).turns[0];
  assert.equal(turn.status, "waiting");
  assert.deepEqual(turnHeadline(turn), { status: "waiting", title: "Aguardando sua resposta", detail: "Posso publicar?" });
});

test("old turns keep their own outcome, independent of the live status", () => {
  const events = [
    ev("user_message", { content: "um" }),
    ev("tool_call", { name: "shell_run", params: { command: "ls" } }),
    ev("agent_status", { status: "stopped" }),
    ev("user_message", { content: "dois" }),
  ];
  const { turns } = buildActivity(events, { agentStatus: "running" });
  assert.equal(turns[0].status, "interrupted");
  assert.equal(turns[0].actions[0].status, "interrupted");
  assert.equal(turns[1].status, "running");
});

test("repeated reads are grouped and identical polls collapse", () => {
  const events = [ev("user_message", { content: "x" })];
  ["a.py", "b.py", "c.py"].forEach((path, index) => {
    events.push(ev("tool_call", { name: "file_read", params: { path }, call_id: `r${index}` }));
    events.push(ev("tool_result", { name: "file_read", result: { success: true, path, total_lines: 3 }, call_id: `r${index}` }));
  });
  for (let i = 0; i < 4; i += 1) {
    events.push(ev("tool_call", { name: "shell_view", params: { session_id: "s1" }, call_id: `v${i}` }));
    events.push(ev("tool_result", { name: "shell_view", result: { success: true }, call_id: `v${i}` }));
  }
  const groups = groupActions(buildActivity(events, { agentStatus: "done" }).turns[0].actions);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].title, "Consultou 3 arquivos");
  assert.equal(groups[1].single, true);
  assert.equal(groups[1].item.repeats.length, 4);
});

test("turn results list only files actually written and sources actually read", () => {
  const { turns } = buildActivity(site.events, { agentStatus: "done" });
  const results = turnResults(turns.at(-1));
  assert.deepEqual(results.files.map((file) => file.path).sort(), ["index.html", "script.js", "style.css"]);
  assert.equal(results.files.find((file) => file.path === "index.html").change, "created");
});

test("legacy turns with only agent_activity still render without inventing tools", () => {
  const events = [
    ev("user_message", { content: "x" }),
    ev("agent_activity", { kind: "search", title: "Pesquisando fontes", status: "running" }),
  ];
  const turn = buildActivity(events, { agentStatus: "done" }).turns[0];
  assert.equal(turn.actions[0].title, "Pesquisando fontes");
  assert.equal(turn.actions[0].status, "unknown");
});
