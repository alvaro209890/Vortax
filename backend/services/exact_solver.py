import ast
import math
import operator
import re
import unicodedata
from fractions import Fraction
from typing import Any


CODE_ACTION_RE = re.compile(
    r"\b(crie|criar|faca|faça|desenvolva|implemente|gere|corrija|corrigir|"
    r"edite|editar|altere|alterar|publique|publicar|configure|configurar|automatize|"
    r"construa|monte|programa|programe)\b",
    re.IGNORECASE,
)

CODE_TARGET_RE = re.compile(
    r"\b(codigo|código|site|app|software|sistema|script|api|backend|frontend|"
    r"html|css|javascript|js|react|node|python|automacao|automação|bug|erro|falha)\b",
    re.IGNORECASE,
)

RESEARCH_RE = re.compile(
    r"\b(hoje|agora|atual|atuais|ultimo|último|ultimos|últimos|recente|recentes|"
    r"noticia|notícia|preco|preço|cotacao|cotação|versao|versão|agenda|placar|"
    r"comparar|compare|pesquise|procure|site oficial|github|documentacao|documentação)\b",
    re.IGNORECASE,
)

EXACT_RE = re.compile(
    r"\b(matematica|matemática|exatas|calcule|calcular|conta|resultado|resolva|"
    r"resolver|equacao|equação|equacoes|equações|formula|fórmula|algebra|álgebra|"
    r"geometria|trigonometria|derivada|integral|limite|logaritmo|raiz|porcentagem|"
    r"percentual|juros|probabilidade|estatistica|estatística|media|média|mediana|"
    r"matriz|determinante|vetor|fisica|física|quimica|química|velocidade|"
    r"aceleracao|aceleração|forca|força|energia|densidade|massa|volume)\b",
    re.IGNORECASE,
)

ACTION_RE = re.compile(
    r"\b(abra|abrir|clique|clicar|baixe|baixar|instale|instalar|rode|rodar|execute|"
    r"executar|publique|publicar|configure|configurar|mande|enviar|envie|suba|"
    r"corrija|alterar|altere|edite|editar)\b",
    re.IGNORECASE,
)

SIMPLE_DIRECT_RE = re.compile(
    r"\b(oi|ola|olá|bom dia|boa tarde|boa noite|obrigad[oa]|valeu|beleza|"
    r"me fale|fale sobre|conte|explique|resuma|defina|traduza|reescreva|"
    r"melhore esse texto|corrija esse texto|qual e|qual é|quem e|quem é|"
    r"o que e|o que é|como funciona|por que|porque)\b",
    re.IGNORECASE,
)

ARITHMETIC_SIGNAL_RE = re.compile(r"(\d\s*[-+*/^×÷]\s*\d|\d\s*x\s*\d|=\s*[-+]?\d|[-+]?\d\s*%)", re.IGNORECASE)

CONVERSATIONAL_DIRECT_RE = re.compile(
    r"\b("
    r"oi|ola|e ai|opa|salve|bom dia|boa tarde|boa noite|tudo bem|td bem|"
    r"obrigado|obrigada|valeu|beleza|ok|okay|sim|nao|não|teste|"
    r"qual (?:e |é |eh )?(?:o )?seu nome|qual (?:e |é |eh )?(?:o )?teu nome|"
    r"como (?:voce|você|vc|tu) (?:se )?chama|quem (?:e|é|eh) (?:voce|você|vc|tu)|"
    r"o que (?:voce|você|vc) faz|quem (?:e|é|eh) o vortax|"
    r"voce (?:pode|consegue) me ajudar|você (?:pode|consegue) me ajudar"
    r")\b",
    re.IGNORECASE,
)

SHORT_QUESTION_START_RE = re.compile(
    r"^(?:"
    r"qual|quais|quem|o que|oque|como|por que|porque|"
    r"me diga|me fala|me explique|explique|defina|resuma"
    r")\b",
    re.IGNORECASE,
)

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_FUNCS = {
    "abs": abs,
    "ceil": math.ceil,
    "cos": math.cos,
    "floor": math.floor,
    "ln": math.log,
    "log": math.log,
    "log10": math.log10,
    "round": round,
    "sin": math.sin,
    "sqrt": math.sqrt,
    "tan": math.tan,
}

_CONSTANTS = {
    "e": math.e,
    "pi": math.pi,
}


class ExactSolveError(ValueError):
    pass


def is_code_creation_request(text: str) -> bool:
    value = text or ""
    return bool(CODE_ACTION_RE.search(value) and CODE_TARGET_RE.search(value))


def is_current_or_research_request(text: str) -> bool:
    return bool(RESEARCH_RE.search(text or ""))


def is_exact_prompt(text: str) -> bool:
    value = (text or "").strip()
    if not value or is_code_creation_request(value):
        return False
    return bool(EXACT_RE.search(value) or ARITHMETIC_SIGNAL_RE.search(value))


def _plain_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def is_simple_conversational_prompt(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    plain = _plain_text(value)
    word_count = len(re.findall(r"\w+", plain))
    if word_count <= 4 and CONVERSATIONAL_DIRECT_RE.search(plain):
        return True
    if word_count <= 14 and SHORT_QUESTION_START_RE.search(plain):
        return True
    return False


def should_answer_directly(text: str) -> bool:
    value = (text or "").strip()
    if not value or is_code_creation_request(value) or is_current_or_research_request(value):
        return False
    if is_exact_prompt(value):
        return True
    if len(value) > 260 or ACTION_RE.search(value):
        return False
    if is_simple_conversational_prompt(value):
        return True
    if SIMPLE_DIRECT_RE.search(value):
        return True
    return bool(re.search(r"\?$", value))


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def _format_number(value: float) -> str:
    if not math.isfinite(value):
        return str(value)
    if abs(value - round(value)) < 1e-10:
        return str(int(round(value)))
    fraction = Fraction(value).limit_denominator(10000)
    if abs(float(fraction) - value) < 1e-10 and fraction.denominator <= 1000:
        return f"{fraction.numerator}/{fraction.denominator} ({value:.10g})"
    return f"{value:.10g}"


def _normalize_expr(expr: str, *, equation: bool = False) -> str:
    normalized = expr.strip().lower()
    replacements = {
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "*",
        "÷": "/",
        "^": "**",
        "π": "pi",
        "raiz quadrada": "sqrt",
        "raiz": "sqrt",
        "seno": "sin",
        "cosseno": "cos",
        "tangente": "tan",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)
    normalized = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", normalized)
    if not equation:
        normalized = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", normalized)
    normalized = re.sub(r"(\d)\s+(?=\d)", r"\1", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=sqrt\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=sin\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=cos\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=tan\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=log\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=ln\s*\()", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=pi\b|e\b)", r"\1*", normalized)
    normalized = re.sub(r"(\d|\))\s*(?=x\b)", r"\1*", normalized)
    normalized = re.sub(r"(?<=x)\s*(?=\d|\()", "*", normalized)
    normalized = re.sub(r"\)\s*(?=\d|x\b|pi\b|e\b|\()", ")*", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ExactSolveError("Constante nao numerica.")
    if isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        if node.id in _CONSTANTS:
            return float(_CONSTANTS[node.id])
        raise ExactSolveError(f"Nome nao permitido: {node.id}.")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ExactSolveError("Operador nao permitido.")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if op_type is ast.Pow and abs(right) > 20:
            raise ExactSolveError("Expoente grande demais.")
        return float(_BIN_OPS[op_type](left, right))
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ExactSolveError("Operador unario nao permitido.")
        return float(_UNARY_OPS[op_type](_eval_node(node.operand, variables)))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ExactSolveError("Funcao nao permitida.")
        args = [_eval_node(arg, variables) for arg in node.args]
        if len(args) > 2:
            raise ExactSolveError("Muitos argumentos.")
        return float(_FUNCS[node.func.id](*args))
    raise ExactSolveError("Expressao nao suportada.")


def _safe_eval(expr: str, variables: dict[str, float] | None = None) -> float:
    normalized = _normalize_expr(expr, equation=bool(variables))
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ExactSolveError("Expressao invalida.") from exc
    return _eval_node(tree, variables or {})


def _extract_equation(text: str) -> str | None:
    candidates = re.findall(r"[-+*/^().,%\s\dxX=×÷−–—]+", text)
    for candidate in candidates:
        value = candidate.strip(" .,:;!?")
        if "=" in value and re.search(r"\bx\b|[0-9]x|x[0-9(]", value, re.IGNORECASE):
            return value
    return None


def _solve_equation(equation: str) -> dict[str, Any] | None:
    left, right = equation.split("=", 1)
    normalized = _normalize_expr(f"({left})-({right})", equation=True)
    if re.search(r"\b(sin|cos|tan|log|ln|sqrt)\b", normalized):
        return None

    def f(x_value: float) -> float:
        return _safe_eval(normalized, {"x": x_value})

    y0 = f(0.0)
    y1 = f(1.0)
    y2 = f(2.0)
    a = (y2 - 2 * y1 + y0) / 2
    b = y1 - y0 - a
    c = y0

    roots: list[float] = []
    if abs(a) < 1e-10:
        if abs(b) < 1e-10:
            return None
        roots = [(-c) / b]
    else:
        discriminant = b * b - 4 * a * c
        if discriminant < -1e-10:
            return {
                "status": "solved",
                "answer": "sem raizes reais",
                "steps": [
                    f"Equacao normalizada: {normalized} = 0",
                    f"Discriminante: {_format_number(discriminant)}",
                ],
                "confidence": "medium",
                "kind": "equation",
            }
        discriminant = max(discriminant, 0.0)
        sqrt_delta = math.sqrt(discriminant)
        roots = [(-b - sqrt_delta) / (2 * a), (-b + sqrt_delta) / (2 * a)]

    valid_roots = [root for root in roots if abs(f(root)) < 1e-7]
    if not valid_roots:
        return None
    formatted_roots = sorted({_format_number(root) for root in valid_roots})
    answer = "x = " + " ou x = ".join(formatted_roots)
    return {
        "status": "solved",
        "answer": answer,
        "steps": [
            f"Equacao normalizada: {normalized} = 0",
            f"Coeficientes aproximados: a={_format_number(a)}, b={_format_number(b)}, c={_format_number(c)}",
            f"Raiz(es): {answer}",
        ],
        "confidence": "high",
        "kind": "equation",
    }


def _extract_arithmetic_expression(text: str) -> str | None:
    sqrt_match = re.search(r"raiz(?:\s+quadrada)?\s+de\s+(-?\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
    if sqrt_match:
        return f"sqrt({sqrt_match.group(1)})"

    candidates = re.findall(r"[-+*/^().,%\s\d×÷−–—xX]+", text)
    useful: list[str] = []
    for candidate in candidates:
        value = candidate.strip(" .,:;!?")
        if len(value) < 3:
            continue
        if "=" in value:
            continue
        if ARITHMETIC_SIGNAL_RE.search(value):
            useful.append(value)
    if not useful:
        return None
    return max(useful, key=len)


def solve_exact_problem(problem: str, context: str | None = None) -> dict[str, Any]:
    text = "\n".join(part for part in (problem, context or "") if part).strip()
    if not text:
        return {"status": "needs_model", "answer": "", "steps": [], "confidence": "low", "kind": "empty"}

    percent = re.search(
        r"(-?\d+(?:[,.]\d+)?)\s*%\s*(?:de|do|da|dos|das|of)\s*(-?\d+(?:[,.]\d+)?)",
        text,
        re.IGNORECASE,
    )
    if percent:
        pct = _to_float(percent.group(1))
        base = _to_float(percent.group(2))
        result = base * pct / 100
        return {
            "status": "solved",
            "answer": _format_number(result),
            "steps": [
                f"Converter porcentagem: {_format_number(pct)}% = {_format_number(pct / 100)}",
                f"Multiplicar por {_format_number(base)}: {_format_number(base)} * {_format_number(pct / 100)} = {_format_number(result)}",
            ],
            "confidence": "high",
            "kind": "percentage",
        }

    equation = _extract_equation(text)
    if equation:
        try:
            solved_equation = _solve_equation(equation)
        except ExactSolveError:
            solved_equation = None
        if solved_equation:
            return solved_equation

    expression = _extract_arithmetic_expression(text)
    if expression:
        try:
            result = _safe_eval(expression)
        except (ArithmeticError, ExactSolveError, ValueError):
            result = None
        if result is not None:
            normalized = _normalize_expr(expression)
            return {
                "status": "solved",
                "answer": _format_number(result),
                "steps": [f"Expressao: {normalized}", f"Resultado: {_format_number(result)}"],
                "confidence": "high",
                "kind": "arithmetic",
            }

    return {
        "status": "needs_model",
        "answer": "",
        "steps": [],
        "confidence": "low",
        "kind": "exact_reasoning",
        "reason": "Nao foi possivel resolver de forma deterministica; encaminhe para resposta direta do modelo com o contexto extraido.",
    }


def format_exact_answer(result: dict[str, Any]) -> str:
    if result.get("status") != "solved":
        return str(result.get("reason") or "Nao consegui resolver automaticamente.")
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    lines = [f"Resultado: {result.get('answer')}"]
    if steps:
        lines.append("")
        lines.append("Passos:")
        lines.extend(f"- {step}" for step in steps)
    return "\n".join(lines)
