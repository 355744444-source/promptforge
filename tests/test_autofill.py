"""Unit tests for the offline auto-continuation engine (no Qt needed)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pforge.autofill import analyze, expand, extract_subject  # noqa: E402
from pforge.model import LENGTHS, PromptSpec  # noqa: E402


class TestIntent(unittest.TestCase):
    def test_code_task(self):
        self.assertEqual(analyze("给现有查询接口加分页参数，调用方不改代码").key, "code")

    def test_copy_task(self):
        self.assertEqual(analyze("帮我写一份小红书文案，介绍新款内存条").key, "copy")

    def test_review_beats_object_word(self):
        # 「评审代码」要的是评审档，不是写代码档
        self.assertEqual(analyze("评审这段 Python 代码的错误处理").key, "review")

    def test_record_beats_review_word(self):
        # 「整理评审会纪要」要的是纪要档
        self.assertEqual(analyze("整理昨天产品评审会的会议记录").key, "summary")

    def test_fallback_profile(self):
        self.assertEqual(analyze("随便看看").key, "generic")

    def test_every_profile_is_reachable(self):
        seeds = {
            "code": "写一段 Python 代码",
            "copy": "写一篇产品文案",
            "data": "分析这份销售报表",
            "review": "评审这份设计稿",
            "plan": "制定一份上线计划",
            "summary": "总结这次会议",
            "translate": "翻译这段英文",
            "explain": "讲解一下什么是索引",
            "email": "写一封邮件给客户",
        }
        for key, seed in seeds.items():
            self.assertEqual(analyze(seed).key, key, seed)
        self.assertEqual(analyze("帮我理一理这件事").key, "generic")


class TestSubject(unittest.TestCase):
    def test_strips_polite_and_verb(self):
        # 「介绍」只是引导动词，不是对象本身
        self.assertEqual(extract_subject("帮我写一份小红书文案，介绍新款内存条"), "新款内存条")

    def test_strips_count_prefix(self):
        self.assertEqual(extract_subject("生成 3 个版本的公众号标题，重点突出性价比"), "公众号标题")

    def test_keeps_count_when_it_is_the_whole_subject(self):
        self.assertEqual(extract_subject("给我 3 个方案"), "3 个方案")

    def test_strips_give_pattern(self):
        self.assertEqual(extract_subject("给运营团队写一份双十一活动方案，两周内上线"), "双十一活动方案")

    def test_strips_ba_pattern(self):
        self.assertEqual(extract_subject("把这段英文产品说明翻译成中文"), "这段英文产品说明")

    def test_strips_manner_prefix(self):
        self.assertEqual(extract_subject("用通俗的方式讲清什么是内存时序"), "什么是内存时序")

    def test_keeps_short_phrase_intact(self):
        self.assertEqual(extract_subject("写个请假条"), "请假条")

    def test_empty_falls_back(self):
        self.assertTrue(extract_subject("   "))

    def test_long_phrase_is_capped(self):
        self.assertLessEqual(len(extract_subject("写" + "很长的需求" * 20)), 31)


class TestExpand(unittest.TestCase):
    def test_empty_task_changes_nothing(self):
        spec = PromptSpec()
        result = expand(spec)
        self.assertFalse(result.changed)
        self.assertTrue(result.spec.is_blank())

    def test_fills_blank_fields(self):
        result = expand(PromptSpec(task="给运营团队写一份双十一活动方案，两周内上线"))
        s = result.spec
        self.assertEqual(s.role, "资深项目经理")
        self.assertTrue(s.background)
        self.assertTrue(s.audience)
        self.assertTrue(s.success)
        self.assertTrue(s.out_schema)
        self.assertTrue(s.must_have)
        self.assertTrue(s.avoid)
        self.assertTrue(s.filled_examples)
        self.assertEqual(len(s.filled_steps), 4)

    def test_never_overwrites_existing_text(self):
        spec = PromptSpec(
            task="帮我写一份小红书文案，介绍新款 DDR5 6400 内存条",
            role="我自己写的角色",
            background="我自己写的背景",
            audience="我自己写的读者",
            success="我自己写的标准",
            out_schema="我自己写的结构",
            must_have="我自己写的必含",
            avoid="我自己写的禁止",
            tone="幽默风趣",
            styles=["学术中立"],
            length=LENGTHS[0],
            style_sample="我自己写的文风",
        )
        result = expand(spec)
        s = result.spec
        self.assertEqual(s.role, "我自己写的角色")
        self.assertEqual(s.background, "我自己写的背景")
        self.assertEqual(s.audience, "我自己写的读者")
        self.assertEqual(s.success, "我自己写的标准")
        self.assertEqual(s.out_schema, "我自己写的结构")
        self.assertEqual(s.must_have, "我自己写的必含")
        self.assertEqual(s.avoid, "我自己写的禁止")
        self.assertEqual(s.tone, "幽默风趣")
        self.assertEqual(s.styles, ["学术中立"])
        self.assertEqual(s.length, LENGTHS[0])
        self.assertEqual(s.style_sample, "我自己写的文风")
        # 空白项仍然会被补
        self.assertTrue(s.filled_steps)
        self.assertTrue(s.filled_examples)

    def test_existing_examples_and_steps_are_kept(self):
        from pforge.model import Example, StepItem

        spec = PromptSpec(
            task="写一篇产品文案",
            examples=[Example("我的范例", "输入", "输出")],
            steps=[StepItem("我的步骤", "说明")],
        )
        result = expand(spec)
        self.assertEqual(len(result.spec.examples), 1)
        self.assertEqual(result.spec.examples[0].title, "我的范例")
        self.assertEqual(len(result.spec.steps), 1)
        self.assertEqual(result.spec.steps[0].title, "我的步骤")

    def test_second_run_is_noop(self):
        first = expand(PromptSpec(task="写一份双十一活动方案，两周内上线")).spec
        second = expand(first)
        self.assertFalse(second.changed)

    def test_does_not_mutate_input(self):
        spec = PromptSpec(task="写一份双十一活动方案，两周内上线")
        expand(spec)
        self.assertEqual(spec.role, "")
        self.assertEqual(spec.examples, [])
        self.assertEqual(spec.steps, [])

    def test_explicit_tone_and_language_hints(self):
        result = expand(PromptSpec(task="把这段说明翻译成英文，语气幽默一点"))
        self.assertEqual(result.spec.tone, "幽默风趣")
        self.assertEqual(result.spec.language, "English")

    def test_length_hint(self):
        result = expand(PromptSpec(task="写一段产品介绍，要详细"))
        self.assertEqual(result.spec.length, LENGTHS[2])

    def test_short_task_skips_steps(self):
        # 简单任务不该被拆成 4 步
        self.assertEqual(len(expand(PromptSpec(task="写个请假条")).spec.filled_steps), 0)

    def test_long_task_gets_steps_even_for_simple_profile(self):
        seed = "写一封邮件通知客户合同变更，说明三个变化点和生效时间"
        self.assertTrue(expand(PromptSpec(task=seed)).spec.filled_steps)

    def test_demo_is_labelled_as_placeholder(self):
        result = expand(PromptSpec(task="写一篇产品文案"))
        self.assertIn("结构骨架", result.spec.examples[0].title)

    def test_filled_labels_are_human_readable(self):
        result = expand(PromptSpec(task="写一份双十一活动方案"))
        self.assertIn("角色", result.filled)
        self.assertIn("背景", result.filled)
        self.assertTrue(all(isinstance(x, str) and x for x in result.filled))


if __name__ == "__main__":
    unittest.main()
