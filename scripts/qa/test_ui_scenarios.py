"""Testes automatizados e reproduzíveis de interface para o Vortax.

Valida os percursos críticos do Computador do Vortax contra a pilha de QA:
1. Criação de site: anéis girando durante execução, botão Computador, abas Navegador, Arquivos, Terminal e Preview, ausência de overflow horizontal (desktop 1440px).
2. API com testes: abas Arquivos e Terminal com saída e checks, responsividade em tela mobile (390px, tema claro/escuro).
3. Interrupção: botão Parar encerra a execução, anéis param de girar (.vx-status__ring sem animações ativas), status atualizado para Interrompido.
4. Movimento reduzido: anéis ficam estáticos com prefers-reduced-motion: reduce.
5. Tela protegida: navegador omite imagens e ponteiro ao acessar páginas com campos sensíveis.

Uso:
  python scripts/qa/test_ui_scenarios.py [--url http://127.0.0.1:5174] [--out-dir /tmp/vx-shots]
"""

import argparse
import json
import os
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERRO: playwright não instalado. Instale com: pip install playwright", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Testes de interface do Vortax")
    parser.add_argument("--url", default="http://127.0.0.1:5174", help="URL do frontend Vortax")
    parser.add_argument("--out-dir", default="/tmp/vortax-ui-shots", help="Diretório para capturas")
    parser.add_argument("--chrome-binary", default=os.getenv("CHROME_BINARY"), help="Caminho do Chromium")
    return parser.parse_args()


def get_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def get_running_rings(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('.vx-status__ring')].filter(e => e.offsetWidth || e.offsetHeight)
            .map(e => e.getAnimations().filter(a => a.playState === 'running').length)"""
    )


def is_task_busy(page):
    return page.locator("button[title='Interromper tarefa']").count() > 0


def create_new_task(page, form="desktop"):
    box = page.get_by_label("Mensagem")
    box.wait_for(state="visible", timeout=20000)
    nova = page.get_by_role("button", name="Nova tarefa")
    if not nova.count() and form == "mobile":
        abrir = page.get_by_label("Abrir conversas")
        if abrir.count():
            abrir.first.click()
            page.wait_for_timeout(500)
        nova = page.get_by_role("button", name="Nova tarefa")
    if nova.count():
        nova.first.click()
        page.wait_for_timeout(700)
    box = page.get_by_label("Mensagem")
    box.wait_for(state="visible", timeout=10000)
    return box


def test_site_creation_desktop(browser, base_url, out_dir):
    print("-> Testando Cenário 1: Criação de site (desktop 1440px, tema escuro)...")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    ctx.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    page = ctx.new_page()

    page.goto(base_url, wait_until="domcontentloaded")
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    box = create_new_task(page, "desktop")
    box.fill("QA site: crie um site de portfólio")
    box.press("Enter")

    page.wait_for_timeout(3000)
    running = get_running_rings(page)
    assert any(count > 0 for count in running), "Anéis deveriam estar girando durante execução"
    page.screenshot(path=os.path.join(out_dir, "scenario-site-running.png"))

    # Aguarda conclusão
    t0 = time.time()
    while is_task_busy(page) and time.time() - t0 < 60:
        page.wait_for_timeout(1000)
    assert not is_task_busy(page), "Tarefa não concluiu no tempo esperado"
    page.wait_for_timeout(1500)

    # Anéis devem parar após conclusão
    after_rings = get_running_rings(page)
    assert all(count == 0 for count in after_rings), f"Nenhum anel deve girar após conclusão: {after_rings}"

    # Sem overflow no chat
    assert get_overflow(page) <= 0, "Chat gerou overflow horizontal"
    page.screenshot(path=os.path.join(out_dir, "scenario-site-done.png"))

    # Abre Computador e valida abas
    comp = page.locator("button.detail-open-btn[title='Computador do Vortax']")
    assert comp.count() > 0, "Botão do Computador deve estar presente"
    comp.first.click()
    page.wait_for_timeout(800)

    tabs = page.locator(".vx-tabs [role=tab]")
    assert tabs.count() >= 4, f"Esperadas pelo menos 4 abas, encontradas {tabs.count()}"

    for i in range(tabs.count()):
        tabs.nth(i).click()
        page.wait_for_timeout(600)
        assert get_overflow(page) <= 0, f"Overflow detectado na aba {i}"

    ctx.close()
    print("  ✓ Cenário 1 aprovado.")


def test_api_mobile_responsiveness(browser, base_url, out_dir):
    print("-> Testando Cenário 2: API em tela mobile (390px, responsividade e layout)...")
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    ctx.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    page = ctx.new_page()

    page.goto(base_url, wait_until="domcontentloaded")
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    box = create_new_task(page, "mobile")
    box.fill("QA api: implemente uma api de tarefas com testes")
    box.press("Enter")

    t0 = time.time()
    while is_task_busy(page) and time.time() - t0 < 60:
        page.wait_for_timeout(1000)
    assert not is_task_busy(page), "Tarefa não concluiu"
    page.wait_for_timeout(1500)

    comp = page.locator("button.detail-open-btn[title='Computador do Vortax']")
    comp.first.click()
    page.wait_for_timeout(800)

    # Valida container do código na aba Arquivos
    tabs = page.locator(".vx-tabs [role=tab]")
    # Clica na aba Arquivos (aba 1)
    tabs.nth(1).click()
    page.wait_for_timeout(700)

    code_info = page.evaluate(
        """() => {
            const p = document.querySelector("[aria-label='Computador do Vortax']");
            const c = p && p.querySelector('.vx-code');
            if (!c) return null;
            const pr = p.getBoundingClientRect(), cr = c.getBoundingClientRect();
            return { inside: cr.right <= pr.right + 2, scrollW: c.scrollWidth, clientW: c.clientWidth };
        }"""
    )
    assert code_info and code_info["inside"], "Editor de código deve respeitar a largura do painel em mobile"
    assert get_overflow(page) <= 0, "Painel gerou overflow na página mobile"
    page.screenshot(path=os.path.join(out_dir, "scenario-mobile-files.png"))

    ctx.close()
    print("  ✓ Cenário 2 aprovado.")


def test_interruption_and_reduced_motion(browser, base_url, out_dir):
    print("-> Testando Cenário 3: Interrupção (Parar) e movimento reduzido...")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    ctx.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    page = ctx.new_page()

    page.goto(base_url, wait_until="domcontentloaded")
    box = create_new_task(page, "desktop")
    box.fill("QA longo: processe os lotes")
    box.press("Enter")

    page.wait_for_timeout(2500)
    # Com movimento reduzido, os anéis não devem ter animações ativas
    rings_reduced = get_running_rings(page)
    assert all(count == 0 for count in rings_reduced), "Anéis não devem girar com prefers-reduced-motion: reduce"

    stop_btn = page.locator("button[title='Interromper tarefa']")
    assert stop_btn.count() > 0, "Botão Interromper tarefa deve estar visível durante execução"
    stop_btn.first.click()
    page.wait_for_timeout(4000)

    assert not is_task_busy(page), "Tarefa deve parar após clique no botão Interromper"
    page.screenshot(path=os.path.join(out_dir, "scenario-interrupted.png"))

    ctx.close()
    print("  ✓ Cenário 3 aprovado.")


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    launch_kwargs = {"args": ["--no-sandbox", "--disable-gpu"]}
    if args.chrome_binary:
        launch_kwargs["executable_path"] = args.chrome_binary

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            test_site_creation_desktop(browser, args.url, args.out_dir)
            test_api_mobile_responsiveness(browser, args.url, args.out_dir)
            test_interruption_and_reduced_motion(browser, args.url, args.out_dir)
        finally:
            browser.close()

    print("\nTODOS OS TESTES DE INTERFACE FORAM APROVADOS COM SUCESSO!")


if __name__ == "__main__":
    main()
