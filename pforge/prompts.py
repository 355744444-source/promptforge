"""Prompt rendering, quality scoring and starter templates."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .model import Example, PromptSpec, StepItem

_LEAD = re.compile(r"^\s*(?:[-*•·]|\d+\s*[.、)）]|[（(]\s*\d+\s*[）)])\s*")


def _bullets(text: str) -> list[str]:
    """Split a free-form list into clean bullet items."""
    items = []
    for raw in text.splitlines():
        line = _LEAD.sub("", raw).strip()
        if line:
            items.append(line)
    return items


def render_prompt(s: PromptSpec) -> str:
    out: list[str] = []
    role = s.role.strip()
    background = s.background.strip()
    audience = s.audience.strip()
    task = s.task.strip()

    if role:
        out += ["# 角色", f"你是一位{role}。", ""]

    if background or audience:
        out.append("# 背景")
        if background:
            out.append(background)
        if audience:
            out.append(f"目标读者：{audience}")
        out.append("")

    if task:
        out += ["# 任务", task, ""]

    success = _bullets(s.success)
    if success:
        out.append("# 成功标准")
        out += [f"- {x}" for x in success]
        out.append("")

    style_lines = []
    if s.tone:
        style_lines.append(f"- 语气：{s.tone}")
    if s.styles:
        style_lines.append(f"- 风格：{'、'.join(s.styles)}")
    style_lines.append(f"- 语言：{s.language}")
    style_lines.append(f"- 篇幅：{s.length}")
    out.append("# 语气与风格")
    out += style_lines
    if s.style_sample.strip():
        out.append("文风示例（模仿它的语感，不要照抄内容）：")
        for line in s.style_sample.strip().splitlines():
            out.append(f"> {line.strip()}" if line.strip() else ">")
    out.append("")

    examples = s.filled_examples
    if examples:
        out.append("# 参考范例")
        out.append(f"以下是 {len(examples)} 组范例，请严格对齐它们的结构、颗粒度和表达方式。")
        for i, ex in enumerate(examples, 1):
            title = ex.title.strip()
            out.append(f"## 范例 {i}" + (f"：{title}" if title else ""))
            if ex.input.strip():
                out.append("输入：")
                out += ex.input.strip().splitlines()
            if ex.output.strip():
                out.append("输出：")
                out += ex.output.strip().splitlines()
        out.append("")

    steps = s.filled_steps
    if steps:
        out.append("# 执行步骤")
        out.append("请按以下步骤推进，不要跳步，也不要合并步骤：")
        for i, st in enumerate(steps, 1):
            detail = st.detail.strip()
            out.append(f"{i}. {st.title.strip()}" + (f"——{detail}" if detail else ""))
        out.append("")

    out.append("# 执行方式")
    out.append(
        {
            "一次性输出": "思考清楚后一次性输出完整结果，中途不要向我提问，也不要输出与结果无关的过程说明。",
            "先给计划，再执行": "先用不超过 5 行写出执行计划，然后直接按计划执行到底，不要停下来等我确认。",
            "分步确认": "先只执行第 1 步并停下来，等我确认后再继续下一步。",
        }.get(s.exec_mode, "")
    )
    out.append("")

    out.append("# 输出要求")
    out.append(f"- 格式：{s.out_format}")
    schema = _bullets(s.out_schema)
    if schema:
        out.append("- 结构：")
        out += [f"  - {x}" for x in schema]
    must = _bullets(s.must_have)
    if must:
        out.append("- 必须包含：")
        out += [f"  - {x}" for x in must]
    avoid = _bullets(s.avoid)
    if avoid:
        out.append("- 不要出现：")
        out += [f"  - {x}" for x in avoid]
    out.append("")

    out.append(
        "如果上面的信息不足以准确完成任务，先提出不超过 3 个最关键的问题；不要用假设代替我的决定。"
    )
    return "\n".join(out).strip() + "\n"


@dataclass
class Check:
    key: str
    label: str
    weight: int
    points: int
    hint: str


# (key, label, weight, tester -> earned points, hint when incomplete)
_CHECKS = [
    (
        "role",
        "角色设定",
        10,
        lambda s: 10 if s.role.strip() else 0,
        "补上「角色」：让 AI 以什么身份说话，会直接决定用词与 judgment 的水平。",
    ),
    (
        "background",
        "背景信息",
        15,
        lambda s: 15 if len(s.background.strip()) >= 20 else (8 if s.background.strip() else 0),
        "背景太薄：补上现状、已有材料、限制条件，AI 才不用靠猜。",
    ),
    (
        "task",
        "核心任务",
        20,
        lambda s: 20 if len(s.task.strip()) >= 12 else (10 if s.task.strip() else 0),
        "任务描述太短：写清「对什么对象、做什么动作、达到什么状态」。",
    ),
    (
        "success",
        "成功标准",
        10,
        lambda s: 10 if _bullets(s.success) else 0,
        "缺少成功标准：给出可验证的判据，AI 才知道什么时候算做完。",
    ),
    (
        "style",
        "语气与风格",
        10,
        lambda s: 10 if (s.tone or s.styles) else 0,
        "选一个语气或风格，避免输出「AI 味」的中间态文体。",
    ),
    (
        "examples",
        "参考范例",
        15,
        lambda s: 15 if len(s.filled_examples) >= 2 else (9 if len(s.filled_examples) == 1 else 0),
        "加 2 组输入/输出范例：范例比形容词更能锁定格式与颗粒度。",
    ),
    (
        "steps",
        "任务拆解",
        15,
        lambda s: 15 if len(s.filled_steps) >= 2 else (8 if len(s.filled_steps) == 1 else 0),
        "把任务拆成 2–5 步：复杂任务不拆解，AI 容易漏掉后半段。",
    ),
    (
        "output",
        "输出要求",
        5,
        lambda s: 5 if s.out_format else 0,
        "指定输出格式（Markdown / 表格 / JSON）。",
    ),
]


def evaluate(s: PromptSpec) -> tuple[int, list[Check], list[str]]:
    checks = []
    total = 0
    for key, label, weight, tester, hint in _CHECKS:
        pts = int(tester(s))
        total += pts
        checks.append(Check(key, label, weight, pts, hint))
    gaps = [c for c in checks if c.points < c.weight]
    gaps.sort(key=lambda c: c.weight - c.points, reverse=True)
    tips = [c.hint for c in gaps][:3]
    if not tips:
        tips = ["结构已经很完整，建议再补 1 组「反例输出」，告诉 AI 什么算不合格。"]
    return total, checks, tips


def score_label(score: int) -> str:
    if score >= 90:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 45:
        return "一般"
    return "待完善"


# --------------------------------------------------------------------------
# starter templates
# --------------------------------------------------------------------------
def _spec(**kw) -> dict:
    return kw


TEMPLATES: list[dict] = [
    {
        "name": "写功能代码",
        "tag": "研发",
        "desc": "带约束、带验收标准的功能实现",
        "spec": _spec(
            role="资深 Python 后端工程师，熟悉 FastAPI 与 PostgreSQL",
            background=(
                "我们的内部订单管理系统基于 FastAPI + PostgreSQL。"
                "目前「导出订单」只支持全量导出，数据超过 5 万条时接口会超时，运营只能分几次手工处理。"
            ),
            audience="接手这段代码的同事",
            task="为订单导出增加「按时间范围 + 状态筛选、分批流式写入 CSV」的能力，改造现有的 /orders/export 接口，并保持旧参数兼容。",
            success="10 万条数据导出时进程内存不超过 300MB\n原有调用方不改代码即可继续使用\nCSV 字段顺序与旧版完全一致",
            tone="专业严谨",
            styles=["清单体"],
            language="简体中文",
            length="适中",
            style_sample="",
            examples=[
                Example(
                    "旧调用方式",
                    "GET /orders/export?all=true",
                    "保持可用；内部自动转为分批逻辑，响应头与字段不变。",
                ),
                Example(
                    "新筛选方式",
                    "GET /orders/export?start=2024-01-01&end=2024-03-31&status=paid",
                    "流式返回 CSV，Content-Disposition 中的文件名包含时间范围。",
                ),
            ],
            steps=[
                StepItem("复述需求与约束", "3 行以内确认目标、不改动的部分、已知限制"),
                StepItem("给出方案", "说明分批策略、参数兼容方式、异常与中断处理"),
                StepItem("输出代码", "按文件给出完整可运行代码，标注改动点"),
                StepItem("自检", "列出边界情况与验证方法"),
            ],
            exec_mode="先给计划，再执行",
            out_format="代码块",
            out_schema="每个文件单独给出：文件路径 + 完整代码",
            must_have="关键改动的行内注释\n旧接口的兼容说明",
            avoid="用省略号代替代码\n引入新的第三方依赖\n「当然可以」「希望这对你有帮助」这类寒暄",
        ),
    },
    {
        "name": "代码审查",
        "tag": "研发",
        "desc": "分级问题清单，只挑问题不重写",
        "spec": _spec(
            role="严格的代码审查者，做过 8 年后端与安全审计",
            background="这是一份准备合并到主干的分支代码，团队里还有两位同学会维护它，所以可读性和边界处理同样重要。",
            audience="提交这段代码的开发者",
            task="审查我提供的代码，找出真正的缺陷、隐患与可维护性问题，并按严重程度分级。",
            success="每个问题都能指到具体行或函数\n每条都给出可执行的修复方向\n没有「建议加注释」这类无意义条目",
            tone="简洁直接",
            styles=["犀利直接", "清单体"],
            language="简体中文",
            length="详尽",
            examples=[
                Example(
                    "合格的条目",
                    "第 42 行 sql 字符串拼接了用户输入",
                    "P0 注入风险：改为参数化查询 cursor.execute(sql, (uid,))。影响面：/api/search 全链路。",
                )
            ],
            steps=[
                StepItem("通读并复述意图", "一句话说明这段代码在做什么，确认理解无误"),
                StepItem("分级列问题", "P0 阻断 / P1 严重 / P2 建议，逐条给位置、原因、修法"),
                StepItem("给结论", "能否合并 + 合并前必须修完的条目"),
            ],
            exec_mode="先给计划，再执行",
            out_format="Markdown",
            out_schema="## 结论 / ## 问题清单（表格：级别 | 位置 | 问题 | 修复方向）/ ## 可以夸一句的地方",
            must_have="每条问题的具体位置\n修复方向要能直接照着改",
            avoid="把整段代码重写一遍\n泛泛而谈的「注意性能」\n对格式问题长篇大论",
        ),
    },
    {
        "name": "小红书/公众号文案",
        "tag": "内容",
        "desc": "带钩子、带节奏的社交文案",
        "spec": _spec(
            role="做过 3 年小红书家居类目的内容操盘手",
            background=(
                "我们是一家做人体工学椅的国产品牌，客单价 1200 元左右，"
                "主要靠小红书和公众号种草。最近主推「久坐腰疼的办公室人群」这个卖点，"
                "竞品都在讲参数，我们想讲体感。"
            ),
            audience="25–35 岁、每天坐 8 小时以上、有过腰疼经历的上班族",
            task="写 3 版小红书笔记文案，每版换一个切入角度，都能直接发布。",
            success="开头 2 行内出现能让人停下来的具体场景\n正文不出现参数堆砌\n结尾有自然的行动引导，不像硬广",
            tone="亲切自然",
            styles=["口语化", "故事化"],
            language="简体中文",
            length="适中",
            style_sample="我坐了三年工位椅，腰是在某个加班的周四突然废掉的。那天我站起来，眼前黑了一下，扶着桌沿缓了半分钟。",
            examples=[
                Example(
                    "标题写法",
                    "人体工学椅推荐",
                    "坐坏腰的第 3 年，我终于承认椅子是有区别的",
                )
            ],
            steps=[
                StepItem("定 3 个角度", "每个角度一句话，说明打的是哪种情绪"),
                StepItem("逐版写正文", "钩子 2 行 + 3 个具体细节 + 收尾引导"),
                StepItem("配标题与话题", "每版 1 个标题 + 5 个话题标签"),
            ],
            exec_mode="先给计划，再执行",
            out_format="Markdown",
            out_schema="## 版本一：角度名 / 标题 / 正文 / 话题标签",
            must_have="具体可感的场景细节\n口语化的短句",
            avoid="「家人们」「绝绝子」这类过时网感词\n绝对化用词（最好、第一）\n大段参数罗列",
        ),
    },
    {
        "name": "数据分析洞察",
        "tag": "分析",
        "desc": "从数据到结论，带置信度",
        "spec": _spec(
            role="电商行业的高级数据分析师",
            background=(
                "我负责一个天猫店的经营分析。这个月 GMV 环比下降 12%，"
                "但访客数只降了 3%，投放费用没有变化。老板要一份能在周会上讲的结论。"
            ),
            audience="不懂数据细节的业务负责人",
            task="分析我提供的数据，找出真实原因，并给出可执行的改进动作。",
            success="结论用业务语言说，不出现统计术语堆砌\n每个结论都标注依据的数据点\n改进动作有优先级和责任岗位",
            tone="专业严谨",
            styles=["书面正式"],
            language="简体中文",
            length="详尽",
            style_sample="",
            examples=[],
            steps=[
                StepItem("校验数据", "先说清口径、时间范围、缺失情况"),
                StepItem("拆解指标", "把 GMV 拆成 访客 × 转化率 × 客单价，定位掉在哪一层"),
                StepItem("给结论", "3 条以内，按影响大小排序"),
                StepItem("给动作", "每条动作写清谁做、多久、看什么指标验证"),
            ],
            exec_mode="先给计划，再执行",
            out_format="Markdown",
            out_schema="## 一句话结论 / ## 拆解过程（表格）/ ## 原因假设与置信度 / ## 行动建议（优先级 | 动作 | 责任岗位 | 验证指标）",
            must_have="结论与数据的对应关系\n不确定性说明",
            avoid="把相关性直接说成因果\n「建议加强运营」这类没法执行的建议",
        ),
    },
    {
        "name": "周报/方案撰写",
        "tag": "职场",
        "desc": "结论先行、能被快速读完",
        "spec": _spec(
            role="在大厂做过多年汇报材料的业务负责人",
            background="我在一家制造企业做信息化，本周主要推进了三件事：MES 与 ERP 的接口联调、两条产线的看板改造、一次数据治理评审。老板只有 3 分钟看这份周报。",
            audience="只看结论、没耐心读过程的总经理",
            task="把下面这堆零散的工作记录，整理成一份结论先行、能快速读完的周报。",
            success="开头 3 行内能看出本周真实进展与风险\n风险有明确的上报诉求\n全篇不超过一屏",
            tone="专业严谨",
            styles=["书面正式", "清单体"],
            language="简体中文",
            length="精简",
            style_sample="",
            examples=[
                Example(
                    "差的写法",
                    "本周参与了接口联调工作，与相关部门沟通…",
                    "MES—ERP 接口已联调 4/6 个场景，卡在库存回写（ERP 侧字段缺失），需 IT 本周内补表。",
                )
            ],
            steps=[
                StepItem("提取结论", "先写 3 行进展摘要，再写风险"),
                StepItem("组织主体", "按「进展 / 风险 / 下周计划 / 需要支持」四段"),
                StepItem("压缩语言", "删掉所有过程性描述，只留结果与数字"),
            ],
            exec_mode="一次性输出",
            out_format="Markdown",
            out_schema="## 本周进展 / ## 风险与求助 / ## 下周计划",
            must_have="量化数据\n需要老板决策的事项单独列出",
            avoid="流水账\n「持续跟进中」这类无信息量的表述",
        ),
    },
    {
        "name": "翻译与润色",
        "tag": "语言",
        "desc": "保留术语与语气的双语处理",
        "spec": _spec(
            role="技术文档译者，长期翻译工程类白皮书",
            background="我们有一批对外发布的技术文档需要从中文翻成英文，读者是欧美客户的技术负责人，术语必须与已有 glossary 一致。",
            audience="欧美客户的技术负责人",
            task="把我提供的中文段落翻译成英文，并保持术语一致、语气克制。",
            success="术语与我给的对照表完全一致\n不出现中式英语的长句\n原文的语气强度不变",
            tone="专业严谨",
            styles=["书面正式"],
            language="English",
            length="适中",
            style_sample="The module must be initialized before any calibration call is issued.",
            examples=[
                Example(
                    "术语处理",
                    "半片电池（Half-cell）",
                    "half-cell，全文统一，不写成 half cell 或 halfcell",
                )
            ],
            steps=[
                StepItem("通读并标注难点", "列出歧义句与专业术语"),
                StepItem("初译", "按段落给出译文"),
                StepItem("自检", "回译关键句，确认语义没有漂移"),
            ],
            exec_mode="一次性输出",
            out_format="Markdown",
            out_schema="## 译文 / ## 术语与疑点说明",
            must_have="术语一致性\n难点句的处理理由",
            avoid="逐字直译导致的长句\n自行增删原文信息",
        ),
    },
    {
        "name": "概念讲解",
        "tag": "学习",
        "desc": "从零讲到能用，带类比",
        "spec": _spec(
            role="擅长把复杂概念讲明白的技术讲师",
            background="我要给团队里刚转岗的同事做一次 30 分钟分享，他们懂基本编程，但没接触过这个概念。",
            audience="有编程基础、但完全没接触过该领域的同事",
            task="把下面这个概念讲清楚，让我能照着讲给同事听。",
            success="全程不用未解释的术语\n至少有 2 个生活化类比\n结尾能回答「所以它能解决什么问题」",
            tone="亲切自然",
            styles=["口语化", "故事化"],
            language="简体中文",
            length="适中",
            style_sample="",
            examples=[],
            steps=[
                StepItem("先讲问题", "先说它要解决什么痛点，不讲定义"),
                StepItem("建立类比", "用日常经验搭一座桥"),
                StepItem("讲机制", "分 2–3 层展开，每层一个例子"),
                StepItem("收口", "一句话总结 + 3 个常见误解"),
            ],
            exec_mode="先给计划，再执行",
            out_format="Markdown",
            out_schema="## 它解决什么问题 / ## 一个类比 / ## 内部怎么运作 / ## 三个误解",
            must_have="可复述的一句话总结\n每个术语首次出现时给解释",
            avoid="一上来就下定义\n用另一个更难的术语解释术语",
        ),
    },
    {
        "name": "会议纪要整理",
        "tag": "职场",
        "desc": "决议、待办、责任人一次到位",
        "spec": _spec(
            role="专业的会议记录员",
            background="这是我们季度经营会的录音转写稿，比较口语化、有重复和跑题，需要在 1 小时内发出会议纪要。",
            audience="参会的部门负责人和没参会的上级",
            task="把这份转写稿整理成可直接群发的会议纪要。",
            success="每个决议都能追溯到原话\n待办事项有责任人和时间\n没结论的议题明确标注「未决」",
            tone="简洁直接",
            styles=["清单体", "书面正式"],
            language="简体中文",
            length="精简",
            style_sample="",
            examples=[
                Example(
                    "待办写法",
                    "大家再对一下吧",
                    "【待办】张伟：本周五前给出 Q3 预算调整版（依据：2:14 讨论）",
                )
            ],
            steps=[
                StepItem("抽议题", "按讨论顺序列出议题名"),
                StepItem("提炼决议", "每个议题只留达成的结论"),
                StepItem("列待办", "事项 + 责任人 + 截止时间"),
            ],
            exec_mode="一次性输出",
            out_format="Markdown",
            out_schema="## 会议信息 / ## 议题与决议 / ## 待办事项（表格：事项 | 责任人 | 截止）/ ## 未决事项",
            must_have="责任人姓名\n未决事项单独成段",
            avoid="保留寒暄与跑题内容\n自己编造没讨论过的结论",
        ),
    },
]


def template_spec(index: int) -> PromptSpec:
    return PromptSpec.from_dict(TEMPLATES[index]["spec"])
