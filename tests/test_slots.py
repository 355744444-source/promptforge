"""槽位抽取与三档补全深度的回归测试。"""
from __future__ import annotations

import unittest

from pforge.autofill import DEPTH_DEEP, DEPTH_QUICK, DEPTH_STANDARD, analyze, expand
from pforge.model import PromptSpec
from pforge.slots import parse


class TestDeadline(unittest.TestCase):
    def test_weeks(self):
        sl = parse("给运营团队写一份双十一活动方案，两周内上线")
        self.assertEqual(sl.deadline, "两周内")
        self.assertEqual(sl.days, 14)

    def test_days(self):
        sl = parse("用 Python 3 天内写个脚本")
        self.assertEqual(sl.days, 3)

    def test_fixed_point_has_no_duration(self):
        sl = parse("本周五前给客户回一封邮件")
        self.assertEqual(sl.deadline, "本周五")
        self.assertEqual(sl.days, 0)

    def test_month_needs_a_deadline_word(self):
        # 「3 月」是月份，不是工期
        self.assertEqual(parse("分析 3 月的销售数据").deadline, "")
        self.assertEqual(parse("3 个月内上线").days, 90)


class TestCount(unittest.TestCase):
    def test_counts_versions(self):
        sl = parse("生成 3 个版本的公众号标题")
        self.assertEqual(sl.count, 3)
        self.assertEqual(sl.count_phrase, "3 个版本")

    def test_ignores_measure_word(self):
        # 「一份文案」是量词
        self.assertEqual(parse("帮我写一份小红书文案").count, 0)

    def test_does_not_swallow_noun(self):
        sl = parse("给新员工写一版 5 条朋友圈招聘文案")
        self.assertEqual(sl.count_phrase, "5 条")


class TestChannel(unittest.TestCase):
    def test_xiaohongshu_brings_rules(self):
        sl = parse("帮我写一份小红书文案，介绍新款内存条")
        self.assertIsNotNone(sl.channel)
        self.assertEqual(sl.channel.name, "小红书")
        text = "".join(sl.channel.always)
        self.assertIn("20 字", text)

    def test_ppt_not_shadowed_by_weekly_report(self):
        self.assertEqual(parse("给老板做一份 PPT 汇报").channel.name, "PPT")

    def test_pages(self):
        self.assertEqual(parse("给老板做一份 PPT 汇报，控制在 10 页").pages, 10)
        self.assertEqual(parse("10 页以内").pages, 10)


class TestAudience(unittest.TestCase):
    def test_team(self):
        self.assertEqual(parse("给运营团队写一份双十一活动方案").audience, "运营团队")

    def test_customer_with_reply_verb(self):
        self.assertEqual(parse("本周五前给客户回一封邮件").audience, "客户")

    def test_skips_pronoun(self):
        self.assertEqual(parse("给我写个请假条").audience, "")


class TestTechAndForbid(unittest.TestCase):
    def test_tech_words(self):
        sl = parse("用 Python 处理这批 Excel 数据")
        self.assertIn("python", sl.tech)
        self.assertIn("excel", sl.tech)

    def test_short_word_needs_boundary(self):
        # go 不能命中 django / google
        self.assertNotIn("golang", parse("用 django 写个接口").tech)

    def test_forbid(self):
        self.assertEqual(parse("不要用 pandas").forbid, ("用 pandas",))

    def test_bie_inside_other_words(self):
        # 「特别 / 区别」里的「别」不是否定词
        self.assertEqual(parse("评审这段代码，特别注意边界情况").forbid, ())

    def test_emphasis(self):
        self.assertEqual(parse("重点突出性价比").emphasis, ("突出性价比",))


class TestDepths(unittest.TestCase):
    seed = "给运营团队写一份双十一活动方案，两周内上线"

    def test_quick_only_fills_the_frame(self):
        result = expand(PromptSpec(task=self.seed), depth=DEPTH_QUICK)
        self.assertTrue(result.spec.role)
        self.assertTrue(result.spec.background)
        self.assertFalse(result.spec.success)
        self.assertFalse(result.spec.filled_steps)
        self.assertFalse(result.spec.filled_examples)

    def test_standard_fills_everything_but_keeps_skeleton(self):
        result = expand(PromptSpec(task=self.seed), depth=DEPTH_STANDARD)
        self.assertTrue(result.spec.success)
        self.assertTrue(result.spec.filled_steps)
        self.assertEqual(len(result.spec.filled_examples), 1)
        self.assertIn("骨架", result.spec.filled_examples[0].title)

    def test_deep_adds_worked_example_and_anti_example(self):
        result = expand(PromptSpec(task=self.seed), depth=DEPTH_DEEP)
        self.assertEqual(len(result.spec.filled_examples), 2)
        self.assertIn("反例", result.spec.filled_examples[1].title)
        self.assertIn("成型", result.spec.filled_examples[0].title)

    def test_deep_has_one_more_step(self):
        standard = expand(PromptSpec(task=self.seed), depth=DEPTH_STANDARD)
        deep = expand(PromptSpec(task=self.seed), depth=DEPTH_DEEP)
        self.assertEqual(len(deep.spec.steps), len(standard.spec.steps) + 1)


class TestSlotDrivenContent(unittest.TestCase):
    def test_deadline_reaches_success(self):
        spec = expand(PromptSpec(task="给运营团队写一份双十一活动方案，两周内上线")).spec
        self.assertIn("两周内", spec.success)

    def test_audience_reaches_success(self):
        spec = expand(PromptSpec(task="给运营团队写一份双十一活动方案，两周内上线")).spec
        self.assertIn("运营团队", spec.success)

    def test_channel_rules_replace_generic_ones(self):
        spec = expand(PromptSpec(task="帮我写一份小红书文案，介绍新款内存条")).spec
        self.assertIn("20 字", spec.success)
        # 「标题」这条已被小红书惯例覆盖，不该再出现一份通用版
        self.assertEqual(sum("标题" in line for line in spec.success.splitlines()), 1)

    def test_forbid_reaches_avoid(self):
        spec = expand(PromptSpec(task="用 Python 写个脚本，不要用 pandas")).spec
        self.assertIn("用 pandas", spec.avoid.splitlines())

    def test_pages_reaches_must_have(self):
        spec = expand(PromptSpec(task="做一份 PPT 汇报，控制在 10 页")).spec
        self.assertIn("总页数 ≤ 10", spec.must_have.splitlines())

    def test_no_placeholder_left_in_examples(self):
        for depth in (DEPTH_STANDARD, DEPTH_DEEP):
            spec = expand(PromptSpec(task="整理昨天的会议记录"), depth=depth).spec
            for ex in spec.filled_examples:
                self.assertNotIn("{", ex.input + ex.output)

    def test_slots_survive_in_result(self):
        result = expand(PromptSpec(task="两周内给运营团队写活动方案"))
        self.assertIn("两周内", result.summary)


class TestIntentWithChannel(unittest.TestCase):
    def test_ppt_report_is_not_email(self):
        # 「汇报」曾让 PPT 需求被判成写邮件
        self.assertEqual(analyze("给老板做一份 PPT 汇报，下周一要").key, "summary")

    def test_script_request_is_code(self):
        self.assertEqual(analyze("用 Python 3 天内写个脚本，清洗这批 Excel 数据").key, "code")

    def test_email_still_email(self):
        self.assertEqual(analyze("本周五前给客户回一封邮件").key, "email")


if __name__ == "__main__":
    unittest.main()
