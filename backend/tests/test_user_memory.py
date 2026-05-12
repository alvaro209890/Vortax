"""Testes para o servico de memorias do usuario (user_memory.py)."""

import pytest

from services.user_memory import (
    add_memory,
    auto_save_from_message,
    delete_memory,
    format_for_system_prompt,
    handle_remember_command,
    list_memories,
    search_memories,
    update_memory,
)


TEST_USER_ID = "test_user_memory_123"


def test_add_and_list_memories():
    mid = add_memory(TEST_USER_ID, "fact", "profissao", "desenvolvedor fullstack", priority=8)
    assert mid > 0

    memories = list_memories(TEST_USER_ID)
    assert len(memories) >= 1
    assert any(m["key"] == "profissao" for m in memories)

    # Limpar
    delete_memory(mid, TEST_USER_ID)


def test_add_memory_invalid_type():
    with pytest.raises(ValueError):
        add_memory(TEST_USER_ID, "invalid_type", "chave", "valor")


def test_update_memory():
    mid = add_memory(TEST_USER_ID, "preference", "estilo", "respostas curtas", priority=5)
    assert update_memory(mid, TEST_USER_ID, "respostas longas", priority=9)
    memories = list_memories(TEST_USER_ID)
    updated = next((m for m in memories if m["id"] == mid), None)
    assert updated is not None
    assert updated["content"] == "respostas longas"
    assert updated["priority"] == 9

    delete_memory(mid, TEST_USER_ID)


def test_delete_memory():
    mid = add_memory(TEST_USER_ID, "context", "temp", "dado temporario")
    assert delete_memory(mid, TEST_USER_ID)
    assert not delete_memory(mid, TEST_USER_ID)  # ja foi deletada


def test_search_memories():
    mid = add_memory(TEST_USER_ID, "fact", "stack", "Python + React + SQLite", priority=7)
    results = search_memories(TEST_USER_ID, "python react")
    assert any(r["id"] == mid for r in results)
    delete_memory(mid, TEST_USER_ID)


def test_format_for_system_prompt_empty():
    result = format_for_system_prompt("usuario_inexistente_xyz")
    assert result == ""


def test_format_for_system_prompt():
    mids = []
    mids.append(add_memory(TEST_USER_ID, "preference", "idioma", "portugues brasileiro", priority=10))
    mids.append(add_memory(TEST_USER_ID, "fact", "profissao", "engenheiro de software", priority=8))

    result = format_for_system_prompt(TEST_USER_ID)
    assert "portugues brasileiro" in result.lower()
    assert "engenheiro" in result.lower()
    assert "MEMORIAS DO USUARIO" in result

    for mid in mids:
        delete_memory(mid, TEST_USER_ID)


def test_auto_save_preference():
    saved = auto_save_from_message(TEST_USER_ID, "eu prefiro respostas em portugues brasileiro com exemplos de codigo")
    assert saved
    memories = list_memories(TEST_USER_ID, memory_type="preference")
    assert any("portugues" in m["content"].lower() for m in memories)

    # Limpar
    for m in memories:
        delete_memory(m["id"], TEST_USER_ID)


def test_auto_save_fact():
    saved = auto_save_from_message(TEST_USER_ID, "sou desenvolvedor backend especializado em Python e Go")
    assert saved
    memories = list_memories(TEST_USER_ID, memory_type="fact")
    assert any("desenvolvedor" in m["content"].lower() for m in memories)

    for m in memories:
        delete_memory(m["id"], TEST_USER_ID)


def test_auto_save_no_pattern():
    saved = auto_save_from_message(TEST_USER_ID, "pesquise noticias sobre IA hoje")
    assert not saved


def test_handle_remember_command_list():
    # Garantir pelo menos uma memoria
    mid = add_memory(TEST_USER_ID, "fact", "teste", "memoria de teste")
    response = handle_remember_command(TEST_USER_ID, "/remember listar")
    assert response
    assert "teste" in response.lower()
    delete_memory(mid, TEST_USER_ID)


def test_handle_remember_command_save():
    response = handle_remember_command(TEST_USER_ID, "/remember [fact] cidade: Sao Paulo")
    assert response
    assert "salva" in response.lower()
    assert "cidade" in response.lower()

    # Verificar que foi salva
    memories = list_memories(TEST_USER_ID)
    saved = next((m for m in memories if m["key"] == "cidade"), None)
    assert saved is not None

    delete_memory(saved["id"], TEST_USER_ID)


def test_handle_remember_command_delete():
    mid = add_memory(TEST_USER_ID, "context", "para_remover", "vai sumir", priority=1)
    response = handle_remember_command(TEST_USER_ID, f"/remember esqueca {mid}")
    assert response
    assert "removida" in response.lower()
    assert not delete_memory(mid, TEST_USER_ID)  # Ja foi deletada


def test_handle_remember_command_not_a_command():
    response = handle_remember_command(TEST_USER_ID, "pesquise algo")
    assert response is None
