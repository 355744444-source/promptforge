"""Unit tests for the pure-Python core (no Qt needed)."""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pforge.model import Example, PromptSpec, StepItem  # noqa: E402
from pforge.prompts import (  # noqa: E402
    TEMPLATES,
    _bullets,
    evaluate,
    render_prompt,
    score_label,
    template_spec,
)


def full_spec() -> PromptSpec:
    return PromptSpec(
        role="资深后端工程师",
        background="我们在维护一个订单系统，导出接口在数据量大时会超时。",
        audience="接手代码的同事",
        task="为导出接口增加分批流式写入能力，并兼容旧参数。",
        success="10 万条不超时\n旧调用方无需改代码",
        tone="专业严谨",
        styles=["清单体"],
        language="简体中文",
        length="适中",
        style_sample="先给结论，再给依据。",
        examples=[
            Example("旧调用", "GET /export?all=true", "保持可用"),
            Example("新调用", "GET /export?start=2024-01-01", "流式返回 CSV"),
        ],
        steps=[StepItem("复述需求", "确认边界"), StepItem("输出代码", "标注改动点")],
        exec_mode="先给计划，再执行",
        out_format="Markdown",
        out_schema="先结论后依据",
        must_have="数据依据",
        avoid="空话套话",
    )


class TestRender(unittest.TestCase):
    def test_sections_in_order(self):
        text = render_prompt(full_spec())
        headers = [line for line in text.splitlines() if line.startswith("# ")]
        self.assertEqual(
            headers,
            ["# 角色", "# 背景", "# 任务", "# 成功标准", "# 语气与风格", "# 参考范例", "# 执行步骤", "# 执行方式", "# 输出要求"],
        )

    def test_role_sentence(self):
        self.assertIn("你是一位资深后端工程师。", render_prompt(full_spec()))

    def test_bullets_from_multiline(self):
        text = render_prompt(full_spec())
        self.assertIn("- 10 万条不超时", text)
        self.assertIn("- 旧调用方无需改代码", text)

    def test_examples_rendered_with_index(self):
        text = render_prompt(full_spec())
        self.assertIn("## 范例 1：旧调用", text)
        self.assertIn("## 范例 2：新调用", text)
        self.assertIn("输入：", text)
        self.assertIn("输出：", text)

    def test_steps_numbered(self):
        text = render_prompt(full_spec())
        self.assertIn("1. 复述需求——确认边界", text)
        self.assertIn("2. 输出代码——标注改动点", text)

    def test_mode_variants(self):
        spec = full_spec()
        spec.exec_mode = "分步确认"
        self.assertIn("先只执行第 1 步", render_prompt(spec))
        spec.exec_mode = "一次性输出"
        self.assertIn("一次性输出完整结果", render_prompt(spec))

    def test_blank_examples_and_steps_are_skipped(self):
        spec = PromptSpec(role="文案", task="写一条朋友圈")
        text = render_prompt(spec)
        self.assertNotIn("# 参考范例", text)
        self.assertNotIn("# 执行步骤", text)
        self.assertIn("# 语气与风格", text)

    def test_unfilled_example_ignored(self):
        spec = full_spec()
        spec.examples.append(Example())
        text = render_prompt(spec)
        self.assertNotIn("范例 3", text)

    def test_no_empty_trailing_lines(self):
        text = render_prompt(full_spec())
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\n\n\n", text)


class TestScore(unittest.TestCase):
    def test_full_spec_scores_100(self):
        score, checks, tips = evaluate(full_spec())
        self.assertEqual(score, 100)
        self.assertTrue(all(c.points == c.weight for c in checks))

    def test_blank_spec_scores_low(self):
        score, _, tips = evaluate(PromptSpec())
        self.assertLessEqual(score, 10)
        self.assertTrue(tips)

    def test_single_example_earns_partial(self):
        spec = PromptSpec()
        spec.examples.append(Example("t", "in", "out"))
        _, checks, _ = evaluate(spec)
        example_check = next(c for c in checks if c.key == "examples")
        self.assertLess(example_check.points, example_check.weight)
        self.assertGreater(example_check.points, 0)

    def test_label_thresholds(self):
        self.assertEqual(score_label(95), "优秀")
        self.assertEqual(score_label(75), "良好")
        self.assertEqual(score_label(50), "一般")
        self.assertEqual(score_label(10), "待完善")


class TestSerialisation(unittest.TestCase):
    def test_roundtrip(self):
        spec = full_spec()
        restored = PromptSpec.from_dict(json.loads(json.dumps(spec.to_dict(), ensure_ascii=False)))
        self.assertEqual(restored.to_dict(), spec.to_dict())

    def test_accepts_dataclass_items(self):
        # regression: templates build Example/StepItem objects, not dicts
        spec = template_spec(0)
        self.assertGreaterEqual(len(spec.filled_examples), 2)
        self.assertGreaterEqual(len(spec.filled_steps), 2)

    def test_bad_input_falls_back(self):
        spec = PromptSpec.from_dict(
            {"role": None, "language": "Klingon", "examples": "nope", "steps": [1, 2], "styles": None}
        )
        self.assertEqual(spec.role, "")
        self.assertEqual(spec.language, "简体中文")
        self.assertEqual(spec.examples, [])
        self.assertEqual(spec.steps, [])

    def test_non_dict_input(self):
        spec = PromptSpec.from_dict("garbage")  # type: ignore[arg-type]
        self.assertTrue(spec.is_blank())

    def test_is_blank(self):
        self.assertTrue(PromptSpec().is_blank())
        self.assertFalse(PromptSpec(task="x").is_blank())


class TestTemplates(unittest.TestCase):
    def test_every_template_is_complete(self):
        self.assertEqual(len(TEMPLATES), 8)
        for i, tpl in enumerate(TEMPLATES):
            with self.subTest(template=tpl["name"]):
                spec = template_spec(i)
                self.assertFalse(spec.is_blank())
                self.assertTrue(spec.role.strip())
                self.assertTrue(spec.task.strip())
                self.assertTrue(spec.background.strip())
                self.assertTrue(spec.success.strip())
                self.assertTrue(spec.tone or spec.styles)
                score, _, _ = evaluate(spec)
                self.assertGreaterEqual(score, 85)
                self.assertGreater(len(render_prompt(spec)), 300)


class TestBullets(unittest.TestCase):
    def test_strips_markers(self):
        self.assertEqual(_bullets("- a\n2. b\n（3）c\n• d"), ["a", "b", "c", "d"])

    def test_keeps_plain_sentence(self):
        self.assertEqual(_bullets("一句话"), ["一句话"])

    def test_drops_blank_lines(self):
        self.assertEqual(_bullets("\n\na\n\n"), ["a"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
