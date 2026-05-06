import asyncio

from services.event_bus import EventBus
from services.task_store import TaskStore


async def _wait_if_paused(task_id: str, store: TaskStore, bus: EventBus) -> bool:
    while store.is_paused(task_id):
        if store.is_stopped(task_id):
            return False
        await asyncio.sleep(0.3)
    return not store.is_stopped(task_id)


async def run_mock_task(task_id: str, description: str, store: TaskStore, bus: EventBus) -> None:
    try:
        store.update_status(task_id, "running")
        await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Analisando pedido"})
        await bus.publish(
            task_id,
            "assistant_message_delta",
            {"content": "Vou preparar a execução local e mostrar cada passo no stream."},
        )
        await asyncio.sleep(0.8)

        steps = [
            ("tool_call", {"name": "planner_mock", "description": "Criando plano inicial para a tarefa"}),
            ("tool_result", {"name": "planner_mock", "result": "Plano mockado criado para validar o chat e o WebSocket."}),
            ("agent_status", {"status": "executing", "label": "Executando passos simulados"}),
            ("tool_call", {"name": "browser_mock", "description": "Simulando abertura do Chrome via CDP"}),
            ("screen_frame", {"caption": "Preview simulado da tela local", "image_base64": None}),
            ("tool_result", {"name": "browser_mock", "result": "Chrome CDP ainda não conectado neste corte; evento visual validado."}),
            ("tool_call", {"name": "summary_mock", "description": "Montando resposta final para o chat"}),
        ]

        for event_type, payload in steps:
            if not await _wait_if_paused(task_id, store, bus):
                await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Tarefa parada"})
                return
            await bus.publish(task_id, event_type, payload)
            await asyncio.sleep(0.8)

        result = (
            "Fluxo local validado: o chat criou a tarefa, o backend emitiu eventos em tempo real "
            f"e o stream acompanhou a solicitação: {description}"
        )
        store.update_status(task_id, "done", result=result)
        await bus.publish(task_id, "assistant_message_done", {"content": result})
        await bus.publish(task_id, "agent_status", {"status": "done", "label": "Concluído"})
    except Exception as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro"})
