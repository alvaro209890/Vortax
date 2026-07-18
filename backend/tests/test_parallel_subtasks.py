import asyncio
import unittest

from services.parallel_subtasks import run_parallel


class ParallelSubtasksTests(unittest.TestCase):
    def test_run_parallel_order_and_limit(self):
        async def work(n: int) -> int:
            await asyncio.sleep(0.01)
            return n * 2

        results = asyncio.run(run_parallel([1, 2, 3, 4], work, max_concurrency=2, return_exceptions=False))
        self.assertEqual(results, [2, 4, 6, 8])


if __name__ == "__main__":
    unittest.main()
