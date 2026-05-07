import unittest

from services.exact_solver import (
    format_exact_answer,
    is_exact_prompt,
    should_answer_directly,
    solve_exact_problem,
)


class ExactSolverTests(unittest.TestCase):
    def test_detects_exact_prompt_from_arithmetic(self) -> None:
        self.assertTrue(is_exact_prompt("quanto e 2 + 2?"))
        self.assertTrue(is_exact_prompt("calcule 12% de 250"))

    def test_does_not_treat_software_creation_as_math_answer(self) -> None:
        self.assertFalse(is_exact_prompt("crie uma calculadora de matematica em React"))

    def test_solves_percentage(self) -> None:
        result = solve_exact_problem("calcule 12% de 250")

        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["answer"], "30")

    def test_solves_linear_equation(self) -> None:
        result = solve_exact_problem("Resolva 2x + 3 = 11")

        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["answer"], "x = 4")

    def test_solves_arithmetic_expression(self) -> None:
        result = solve_exact_problem("quanto e (8 + 4) / 3?")

        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["answer"], "4")
        self.assertIn("Resultado: 4", format_exact_answer(result))

    def test_quick_prompt_router_skips_planner_for_simple_questions(self) -> None:
        self.assertTrue(should_answer_directly("o que e HTML?"))
        self.assertTrue(should_answer_directly("oi"))
        self.assertTrue(should_answer_directly("me fale sobre cache em uma frase"))
        self.assertFalse(should_answer_directly("pesquise o preco atual do dolar"))
        self.assertFalse(should_answer_directly("crie um site de restaurante"))


if __name__ == "__main__":
    unittest.main()
