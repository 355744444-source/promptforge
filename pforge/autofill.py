"""Offline auto-continuation: expand one line of requirement into the rest of the spec.

纯本地规则引擎，不联网、不调用任何模型。输入是 `spec.task`，输出是一份
"其余栏位尽量填满" 的新 PromptSpec —— 已有内容的栏位一律保留，只补空白。

分两层：
1. `slots.parse()` 先把这句话里**确定的信息**抽出来（工期 / 数量 / 渠道 /
   受众 / 技术栈 / 禁忌 / 强调点）；
2. 本模块拿这些槽位去改内容 —— 抽到什么就写什么，抽不到才退回领域套路。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import slots as slotlib
from .model import (
    EXEC_MODES,
    LANGUAGES,
    LENGTHS,
    OUT_FORMATS,
    STYLE_OPTIONS,
    TONE_OPTIONS,
    Example,
    PromptSpec,
    StepItem,
)

# 补全深度：精简只给骨架，深入额外压反例与自查
DEPTH_QUICK = "quick"
DEPTH_STANDARD = "standard"
DEPTH_DEEP = "deep"
DEPTHS: tuple[tuple[str, str], ...] = (
    (DEPTH_QUICK, "精简"),
    (DEPTH_STANDARD, "标准"),
    (DEPTH_DEEP, "深入"),
)

# --------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    keywords: tuple[str, ...]
    strong: tuple[str, ...]
    role: str
    background: str
    audience: str
    success: tuple[str, ...]
    tone: str
    styles: tuple[str, ...]
    length: str
    fmt: str
    schema: str
    must_have: tuple[str, ...]
    avoid: tuple[str, ...]
    steps: tuple[tuple[str, str], ...]
    demo: tuple[str, str, str]
    exec_mode: str = EXEC_MODES[1]
    complex_task: bool = False
    # 「深入」档用的成型范例：给 AI 看颗粒度，而不是看占位符
    deep_demo: tuple[str, str, str] | None = None


_GENERIC = Profile(
    key="generic",
    label="通用任务",
    keywords=(),
    strong=(),
    role="该领域的资深从业者",
    background="{subject}这件事此前没有形成统一口径，手上的材料零散，需要在有限时间内给出可用的结果。",
    audience="要拿这份结果直接用的人，没时间看推导过程",
    success=(
        "结论先给，过程在后",
        "关键判断都给出理由，不靠语气词撑场面",
        "不确定的地方明确标出，不假装确定",
    ),
    tone="专业严谨",
    styles=("书面正式",),
    length=LENGTHS[1],
    fmt=OUT_FORMATS[0],
    schema="按「结论 → 依据 → 下一步」组织，先给能直接用的东西。",
    must_have=("明确结论", "支撑依据"),
    avoid=("模棱两可的表述", "未经验证的断言"),
    steps=(),
    demo=(
        "结构骨架 · 换成你的真实样例",
        "背景：{subject}\n我手上的材料：…\n想要的产出：…",
        "结论：…\n依据：① … ② …\n下一步：…",
    ),
)

PROFILES: tuple[Profile, ...] = (
    Profile(
        key="code",
        label="写代码",
        keywords=(
            "代码", "函数", "接口", "脚本", "开发", "编程", "程序", "重构", "bug",
            "单元测试", "算法", "模块", "数据库", "sql", "python", "java", "api",
            "前端", "后端", "编译", "报错", "性能优化",
        ),
        strong=("代码", "重构", "单元测试", "脚本", "写个程序"),
        role="资深软件工程师",
        background=(
            "代码库里已有相关实现和既定风格，本次改动要在此基础上继续演进；"
            "硬约束是不能破坏现有调用方。"
        ),
        audience="后续接手维护的同事，不一定了解本轮上下文",
        success=(
            "代码可直接运行，无语法与类型错误",
            "覆盖正常路径，并至少处理一个边界情况",
            "改动范围可控，不顺手重排无关代码",
        ),
        tone="简洁直接",
        styles=("清单体",),
        length=LENGTHS[2],
        fmt="代码块",
        schema="按「结论/思路 → 完整代码 → 关键改动说明 → 怎么自测」四段输出，代码块标注语言。",
        must_have=("完整可运行的代码", "关键处的错误处理", "一个调用示例"),
        avoid=("省略号占位", "伪代码", "未声明的新依赖"),
        steps=(
            ("读懂现有代码与约束", "先说明当前实现怎么跑、哪些地方不能动。"),
            ("给出方案与影响面", "列出改哪几个文件、会不会影响调用方。"),
            ("实现", "按方案落代码，保持与既有风格一致。"),
            ("自测", "给出可执行的验证步骤与预期结果。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "需求：给现有查询接口加分页参数\n现有代码：<贴 20 行以内>\n约束：调用方不改代码",
            "思路：…\n```python\n…\n```\n自测：① 默认第 1 页 ② 页码越界返回空列表",
        ),
        complex_task=True,
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "需求：给 /api/orders 加分页\n"
            "现状：Flask + SQLAlchemy，一次返回全量，前端要渲染 3000 行\n"
            "约束：老调用方不改代码，不传参数时行为与现在完全一致",
            "思路：page/page_size 都是可选参数，缺省走全量分支，老调用方零改动。\n"
            "```python\n"
            "@bp.get(\"/api/orders\")\n"
            "def list_orders():\n"
            "    page = request.args.get(\"page\", type=int)\n"
            "    if page is None:                      # 老调用方走这里\n"
            "        return jsonify({\"items\": [o.to_dict() for o in _query()]}), 200\n"
            "    size = min(request.args.get(\"page_size\", 50, type=int), 200)\n"
            "    p = _query().paginate(page=page, per_page=size, error_out=False)\n"
            "    return jsonify({\"items\": [o.to_dict() for o in p.items],\n"
            "                    \"total\": p.total, \"page\": page}), 200\n"
            "```\n"
            "改动：只动 orders.py 一个文件，未新增依赖。\n"
            "自测：① 不传参数 → 返回全量、字段与改前一致 ② page=2&page_size=20 → 20 条且\n"
            "total 正确 ③ page=9999 → 200 + 空 items，不是 404",
        ),
    ),
    Profile(
        key="copy",
        label="写文案",
        keywords=(
            "文案", "小红书", "公众号", "朋友圈", "种草", "推广", "营销", "标题",
            "广告", "海报", "短视频", "口播", "详情页", "推文", "软文", "宣传",
            "slogan", "品牌语", "带货", "笔记",
        ),
        strong=("文案", "小红书", "种草"),
        role="资深内容营销策划",
        background=(
            "{subject}的目标人群已有明确替代选择，说服成本高；"
            "手上只有产品资料，还没有统一的表达口径。"
        ),
        audience="刷到就想划走的普通用户，3 秒内决定要不要继续看",
        success=(
            "标题能让人停下来，正文前两句给出继续读的理由",
            "每条主张都有具体细节或数字支撑，不堆形容词",
            "结尾有明确的行动指引，不写「欢迎了解」这类空话",
        ),
        tone="亲切自然",
        styles=("口语化", "故事化"),
        length=LENGTHS[0],
        fmt="纯文本",
        schema="按「标题 3 版 → 正文 → 结尾行动号召 → 话题标签」输出，每版标题标注它走的角度。",
        must_have=("具体的场景或数字细节", "一个能被记住的记忆点"),
        avoid=("空泛形容词（如「高品质」「超值」）", "夸大或无法验证的承诺"),
        steps=(
            ("提炼差异点", "从材料里挑出 3 个别人没有说过的点。"),
            ("各写一版标题", "三个点各出一条标题，标注走的是哪种角度。"),
            ("展开正文", "挑最优的一条，按场景—解法—行动写正文。"),
            ("收口", "补行动号召与话题标签。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "产品：{subject}\n卖点：① … ② … ③ …\n目标人群：…",
            "标题（≤20 字，含 1 个具体数字）\n正文（3 段：场景痛点 → 怎么解决 → 行动号召）\n结尾：3 个话题标签",
        ),
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "产品：DDR5 6400 32GB 套条\n"
            "真实场景：剪 4K 时时间线一拖就卡，10 分钟素材渲染要等 4 分钟\n"
            "人群：25–35 岁自己攒工作站的剪辑爱好者\n"
            "实测数据：同一工程渲染 4 分 10 秒 → 2 分 40 秒",
            "标题：4K 剪到一半卡住？先别急着换显卡\n"
            "正文：去年配的机器，剪 4K 时间线一拖就卡，我一直以为是显卡带的。\n"
            "后来只换了一对 DDR5 6400 32G，同一个工程从 4 分 10 秒掉到 2 分 40 秒。\n"
            "先去任务管理器看内存占用——超过 80% 再谈换显卡，不然钱白花。\n"
            "结尾：你现在多少 G 内存？把配置发评论区，我帮你看瓶颈卡在哪。\n"
            "#剪辑 #装机 #内存升级",
        ),
    ),
    Profile(
        key="data",
        label="数据分析",
        keywords=(
            "数据", "报表", "统计", "指标", "excel", "表格", "清洗", "漏斗",
            "环比", "同比", "可视化", "bi", "洞察", "留存", "转化率", "分析",
        ),
        strong=("数据分析", "报表", "指标"),
        role="数据分析师",
        background=(
            "{subject}的原始数据分散在多处、口径不统一，"
            "此前给出过的结论因为口径问题被质疑过。"
        ),
        audience="要拿结论做决策的业务负责人，不关心技术细节",
        success=(
            "每个数字都能追溯到来源与口径",
            "先给结论再给支撑，结论不超过 3 条",
            "异常值单独说明，不混进均值里",
        ),
        tone="专业严谨",
        styles=("学术中立", "清单体"),
        length=LENGTHS[2],
        fmt="表格",
        schema="按「结论摘要 → 关键数据表 → 异常与局限 → 下一步建议」组织，列名用业务语言。",
        must_have=("口径说明", "数据来源与时间范围", "至少一条可执行建议"),
        avoid=("只罗列数字不给结论", "没说样本量就下判断"),
        steps=(
            ("定口径与范围", "先说清每个指标怎么算、数据覆盖哪段时间。"),
            ("清洗与校验", "处理缺失与重复，说明剔除了什么。"),
            ("算核心指标", "只留能支撑结论的几个。"),
            ("出结论与建议", "结论在前，建议要能被直接执行。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "数据：{subject}（时间范围 / 样本量）\n想回答的问题：…",
            "结论：① … ② …\n| 维度 | 数值 | 环比 |\n局限：…\n建议：…",
        ),
        complex_task=True,
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "数据：10 月 1–24 日下单流水（口径=支付成功，不含退款）\n"
            "对比：9 月同期\n"
            "想回答的问题：转化率为什么从 2.8% 掉到 2.1%",
            "结论：整体转化下滑 0.7 个点，其中 0.5 个点来自安卓端结算页改版后的报错。\n"
            "| 维度 | 9 月 | 10 月 | 变化 |\n"
            "|---|---|---|---|\n"
            "| 整体转化率 | 2.8% | 2.1% | -0.7pp |\n"
            "| 安卓端结算完成率 | 94% | 88% | -6pp |\n"
            "异常：10/12 安卓客户端 v3.4 上线，结算页报错量当天涨 9 倍。\n"
            "局限：样本为自然流量，不含投放带来的新客。\n"
            "建议：回滚 v3.4 结算页，按 5% 灰度重验后再全量。",
        ),
    ),
    Profile(
        key="review",
        label="评审把关",
        keywords=(
            "评审", "审查", "检查", "review", "挑毛病", "风险", "漏洞", "合规",
            "走查", "找问题", "打分", "验收", "质检",
        ),
        strong=("评审", "审查", "review"),
        role="严格的技术评审专家",
        background=(
            "{subject}已经成型，需要在定稿前找出真正会出问题的地方，"
            "而不是做礼貌性夸奖。"
        ),
        audience="要据此改稿的作者，时间有限，只想知道先改哪几处",
        success=(
            "问题按严重度分级：阻断 / 重要 / 建议",
            "每个问题给出定位 + 为什么是问题 + 具体怎么改",
            "没查到或不确定的部分明确标注，不装作看过",
        ),
        tone="简洁直接",
        styles=("犀利直接", "清单体"),
        length=LENGTHS[2],
        fmt="分点清单",
        schema="按「总体判断 → 阻断级 → 重要 → 建议 → 未覆盖范围」输出。",
        must_have=("严重度分级", "每条问题的定位与修改建议"),
        avoid=("「整体不错」这类空评价", "只说问题不给改法"),
        steps=(
            ("通读建立整体判断", "先给一句总评，说明能不能过。"),
            ("逐项挑问题", "按严重度分级，每条定位到具体位置。"),
            ("给改法", "每条给最小可执行的修改建议。"),
            ("标未覆盖范围", "说明哪些方面本轮没有检查。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "待评审对象：{subject}\n关注点：正确性 / 可维护性 / 风险",
            "总评：建议打回修改\n【阻断】位置 …｜问题 …｜改法 …\n【重要】…\n【建议】…\n未覆盖：…",
        ),
        complex_task=True,
    ),
    Profile(
        key="plan",
        label="方案计划",
        keywords=(
            "方案", "计划", "规划", "排期", "策略", "路线图", "上线", "迁移",
            "落地", "立项", "里程碑", "复盘计划",
        ),
        strong=("方案", "计划", "规划"),
        role="资深项目经理",
        background=(
            "{subject}涉及多方协作，资源和时间都有硬约束，"
            "此前没有统一的目标口径。"
        ),
        audience="需要拍板或配合执行的负责人",
        success=(
            "目标可量化，验收口径写死",
            "每项任务有负责人、前置依赖和预估工期",
            "列出 3 个主要风险及对应的应对动作",
        ),
        tone="专业严谨",
        styles=("清单体",),
        length=LENGTHS[2],
        fmt="表格",
        schema="按「目标与验收 → 分阶段计划表 → 资源与依赖 → 风险与应对 → 回滚方案」输出。",
        must_have=("里程碑与负责人", "风险与应对", "回滚或退出条件"),
        avoid=("只给方向不给步骤", "没有时间点的计划"),
        steps=(
            ("定目标与验收", "一句话目标 + 3 条可检查的验收判据。"),
            ("拆阶段", "按里程碑切成能在{deadline}内交付、每块都能单独验收的段落。"),
            ("排依赖与负责人", "标出串行依赖和卡点。"),
            ("列风险与回滚", "每项风险配一个提前触发信号。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "目标：{subject}\n约束：时间 / 人力 / 预算\n已知卡点：…",
            "目标与验收：…\n| 阶段 | 内容 | 负责人 | 工期 |\n风险：① … 应对 …\n回滚：…",
        ),
        complex_task=True,
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "目标：双十一活动方案，两周内上线\n"
            "约束：预算 8 万，运营 3 人 + 设计 1 人，需走一次风控审核\n"
            "已知卡点：优惠券系统改造还没排期",
            "目标：活动期成交 ≥ 120 万，新客占比 ≥ 35%，上线首日 P0 问题 0。\n"
            "| 阶段 | 内容 | 负责人 | 工期 |\n"
            "|---|---|---|---|\n"
            "| D1–D3 | 定机制与券结构，过风控预审 | 运营 A | 3 天 |\n"
            "| D4–D7 | 页面与素材产出，埋点方案定稿 | 设计 + 运营 B | 4 天 |\n"
            "| D8–D11 | 灰度 10% 流量，盯转化与报错 | 运营 B | 4 天 |\n"
            "| D12–D14 | 全量 + 每日复盘 | 全员 | 3 天 |\n"
            "依赖：券系统改造未排期，是唯一串行卡点。\n"
            "风险：券系统赶不上 → 触发信号 D5 前未定方案，改走平台券兜底，预计损失 15% 折扣力度。\n"
            "回滚：上线 24h 内转化 < 1.2%，降档为全场满减并停止投放。",
        ),
    ),
    Profile(
        key="summary",
        label="总结整理",
        keywords=(
            "总结", "纪要", "会议", "归纳", "提炼", "复盘", "周报", "月报",
            "记录整理", "摘录", "整理一下", "汇报",
        ),
        strong=("会议纪要", "总结", "纪要"),
        role="资深项目助理",
        background=(
            "手上有一份未整理的原始材料（转写稿 / 聊天记录 / 草稿），"
            "信息密度低、重复多。"
        ),
        audience="没参加会议、需要 5 分钟内了解结论和分工的人",
        success=(
            "只留结论、决定、待办，不保留过程闲聊",
            "每条待办都有负责人和时间点，缺的标「待确认」",
            "全文一屏内读完",
        ),
        tone="简洁直接",
        styles=("清单体",),
        length=LENGTHS[0],
        fmt="分点清单",
        schema="按「一句话结论 → 关键决定 → 待办（负责人 / 截止）→ 待确认问题」输出。",
        must_have=("负责人与时间点", "未确认项显式标注"),
        avoid=("逐句复述原文", "编造材料里没提到的结论"),
        steps=(
            ("通读去重", "同类信息合并，删掉寒暄与过程。"),
            ("抽结论与决定", "只保留改变了后续动作的内容。"),
            ("抽待办并落责任人", "缺责任人的标「待确认」。"),
            ("标未决问题", "把悬而未决的点单列。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "原始材料：{subject}的录音转写 / 聊天记录\n参与人：…",
            "结论：…\n决定：① … ② …\n待办：@张三 10/30 前 …\n待确认：…",
        ),
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "原始材料：10/24 产品评审会 47 分钟转写（约 8000 字）\n"
            "参与人：产品 张、研发 李、测试 王",
            "结论：V2.3 只上 3 个功能，其余顺延到 V2.4。\n"
            "决定：① 砍掉批量导入，不阻塞发版 ② 埋点方案 10/27 前定稿\n"
            "待办：@李 10/28 前给批量导入的新排期；@王 10/29 前补埋点验收用例\n"
            "待确认：埋点是否覆盖老版本客户端——会上没结论，需要张总确认",
        ),
    ),
    Profile(
        key="translate",
        label="翻译润色",
        keywords=(
            "翻译", "润色", "改写", "校对", "中译英", "英译中", "语病",
            "措辞", "通顺", "重写这段",
        ),
        strong=("翻译", "润色", "校对"),
        role="母语级双语编辑",
        background="{subject}现有的译文读起来像机翻，术语和语气都不统一。",
        audience="目标语言的母语读者",
        success=(
            "读起来像母语者写的，没有翻译腔",
            "术语全文统一，首次出现给出原词",
            "不增删原意，不擅自解释",
        ),
        tone="专业严谨",
        styles=("书面正式",),
        length=LENGTHS[1],
        fmt="纯文本",
        schema="先给完整译文，再单列「术语与取舍说明」。",
        must_have=("统一术语表", "保留原文结构与层级"),
        avoid=("逐词直译", "自行增补原文没有的信息"),
        steps=(
            ("通读把握语气", "先判断原文的语域与读者。"),
            ("出初稿", "以意群为单位翻译，不逐词对齐。"),
            ("统一术语", "列出术语表，全文替换一致。"),
            ("回读校订", "隔一遍再读，找翻译腔。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "原文：{subject}\n目标语言：…\n术语表：term=译法",
            "译文：…\n取舍说明：① 某词为何这样译 ② 省略了哪个无法对应的表达",
        ),
    ),
    Profile(
        key="explain",
        label="讲解科普",
        keywords=(
            "讲解", "解释", "科普", "教程", "入门", "原理", "是什么", "怎么理解",
            "通俗", "教会我", "搞懂", "小白",
        ),
        strong=("讲解", "科普", "教程"),
        role="擅长把复杂概念讲给外行听的技术作者",
        background="{subject}概念抽象、术语多，读者看过几篇资料但还没建立直觉。",
        audience="完全没接触过这个领域、但有基本逻辑能力的成年人",
        success=(
            "先用日常类比建立直觉，再给准确定义",
            "不出现未经解释的术语",
            "读完后能自己举一个反例",
        ),
        tone="亲切自然",
        styles=("故事化", "口语化"),
        length=LENGTHS[2],
        fmt=OUT_FORMATS[0],
        schema="按「一句话是什么 → 类比 → 机制拆解（3 层）→ 常见误解 → 自测问题」组织。",
        must_have=("至少一个类比", "层层递进的结构", "一个自测问题"),
        avoid=("堆术语", "大段公式没有解释"),
        steps=(
            ("一句话定义", "先给一个不依赖术语的说法。"),
            ("类比", "找一个读者天天见的场景来对应。"),
            ("分层拆解", "从类比过渡到真实机制，一层只讲一件事。"),
            ("常见误解", "列 2 个最容易被搞错的点。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "概念：{subject}\n读者已知：…\n读者卡在哪：…",
            "一句话：…\n类比：…\n拆解：第 1 层 … / 第 2 层 …\n误解：…\n自测：…",
        ),
    ),
    Profile(
        key="email",
        label="邮件沟通",
        keywords=(
            "邮件", "email", "mail", "回信", "致谢", "道歉", "请假", "申请信",
            "公函", "通知函", "公告", "通知",
        ),
        strong=("邮件", "公告", "通知"),
        role="商务写作顾问",
        background=(
            "这封邮件要在三行内让人看懂要办什么事；收件人是忙人，"
            "只扫主题行和开头两行，剩下的很可能不读。"
        ),
        audience="收件人：决策者，时间稀缺，关心结论和要不要他动手",
        success=(
            "主题行说清动作与截止时间",
            "前两行给出结论，细节放在后面",
            "结尾只有一个明确的下一步",
        ),
        tone="专业严谨",
        styles=("书面正式",),
        length=LENGTHS[0],
        fmt="纯文本",
        schema="主题行 + 称呼 + 结论两行 + 细节（分点）+ 明确下一步 + 落款。",
        must_have=("主题行", "明确的下一步与时间"),
        avoid=("铺垫过长", "一封邮件说三件不相关的事"),
        steps=(
            ("定唯一诉求", "这封邮件只要对方做一件事。"),
            ("写结论两行", "结论 + 需要对方做什么。"),
            ("补必要细节", "只写支撑结论需要的信息。"),
            ("收口", "时间点与致谢，一句话。"),
        ),
        demo=(
            "结构骨架 · 换成你的真实样例",
            "收件人：…\n要对方做的事：{subject}\n截止时间：…",
            "主题：【需确认】… 10/30 前\n王总：\n结论一句 + 需要您做的事一句\n细节两条\n下一步：…\n张三",
        ),
        deep_demo=(
            "成型示例 · 对齐颗粒度，内容换成你的",
            "收件人：客户采购 王经理\n"
            "要对方做的事：确认延期两周后的新交期\n"
            "原因：上游芯片到货延后 12 天",
            "主题：【需确认】PO-2317 交期调整至 11/10，请 10/29 前回复\n"
            "王经理：\n"
            "PO-2317 原定 10/27 交货，现需调整为 11/10，希望您确认能否接受。\n"
            "原因：上游芯片到货延后 12 天，我们已在协调替代批次，不影响贵方 11 月上线。\n"
            "方案：① 11/10 整批交付 ② 11/3 先交 60%，余量 11/10 补齐\n"
            "下一步：请 10/29 前回复选哪个方案；未回复则按 11/10 整批排产。\n"
            "张三",
        ),
    ),
)

# ------------------------------------------------------------------ seed parsing

_POLITE = r"(?:请|麻烦你?|帮我|帮忙|给我|我想|我要|我需要你?|能不能|可不可以|可以帮我|想要)"
_ACTION = (
    r"(?:写|做|生成|输出|整理|分析|总结|翻译|润色|改写|评审|审查|检查|设计|制定|"
    r"规划|拆解|讲解|解释|优化|改一下|改改|弄一下|来个|来一份|出个|出一份)"
)
_COUNT = r"(?:一下|一份|一个|一篇|一段|一条|一张|一封|一件|一套|个|份|篇|段|条|张|封|版|下)"
_LEAD = re.compile(rf"^(?:{_POLITE})*(?:{_ACTION})?(?:{_COUNT})?")
# 「给运营团队写一份…」→ 去掉「给…写」
_GIVE = re.compile(
    r"^(?:给|为|对|向|帮)\s*\S{1,14}?"
    r"(?:写|做|生成|出|输出|整理|设计|制定|规划|分析|评审|发)"
)
# 「把这段说明翻译成…」→ 留下被处理的对象
_BA = re.compile(
    r"^把\s*(.{2,20}?)(?:翻译|润色|改写|校对|改成|提炼)(?:成(?:中文|英文|日文|中文版|英文版))?"
)
# 「用通俗的方式讲清…」→ 去掉方式状语（中间可能带空格，如「用 Python 写」）
_MANNER = re.compile(r"^用[\s\S]{0,14}?(?:讲清|讲一下|讲讲|讲|说清|说明|解释|写|做|出|生成)")
# 「小红书文案，介绍…」→ 去掉前导的体裁词
_FORMAT_LEAD = re.compile(r"^[^，,]{0,8}?(?:文案|稿子|稿件|文章|短文|脚本|标题|正文)[，,、]\s*")
# 「介绍新款内存条」→ 去掉纯引导动词，保留真正的修饰语
_INTRO = re.compile(r"^(?:介绍|推荐|聊聊|讲讲|说说|谈谈|看一下|看看)(?:一下|下)?\s*")
# 「3 个版本的公众号标题」→ 去掉数量前缀（全吃掉时回退，见 extract_subject）
_COUNT_LEAD = re.compile(
    r"^(?:\d{1,3}|[一二两三四五六七八九十]{1,3})\s*(?:个|条|版|篇|种|套)?\s*"
    r"(?:版本|方案|标题|文案|选项|角度)?\s*(?:的)?\s*"
)
_TAIL = re.compile(r"[\s。！!,，、;；:：~～]+$")

_TONE_HINTS = (
    ("幽默风趣", ("幽默", "搞笑", "皮一点", "段子", "有趣")),
    ("温柔鼓励", ("鼓励", "安慰", "共情", "温柔")),
    ("权威笃定", ("权威", "笃定", "有说服力", "专业一点")),
    ("简洁直接", ("简洁", "直接", "干脆", "别废话", "短一点", "精简")),
    ("亲切自然", ("亲切", "接地气", "口语", "轻松", "活泼")),
    ("专业严谨", ("严谨", "正式", "规范", "严肃")),
)
_LENGTH_HINTS = (
    (LENGTHS[0], ("精简", "短一点", "简短", "几句话", "一段话", "别太长", "控制在")),
    (LENGTHS[2], ("详细", "详尽", "全面", "深度", "长文", "细致", "展开讲")),
)
_LANG_HINTS = (
    ("中英双语", ("中英", "双语")),
    ("繁体中文", ("繁体",)),
    ("English", ("英文", "英语", "english")),
)
_PLATFORM_STYLES = (
    ("口语化", ("小红书", "抖音", "快手", "朋友圈", "口播", "短视频")),
    ("故事化", ("公众号", "故事", "长文")),
    ("清单体", ("清单", "要点", "ppt", "幻灯片", "汇报")),
)


def extract_subject(text: str) -> str:
    """把一句需求砍成"对象短语"，用于拼背景与范例。"""
    body = text.strip()
    body = _BA.sub(r"\1", body).strip()
    for _ in range(2):
        body = _GIVE.sub("", body).strip()
        body = _MANNER.sub("", body).strip()
    body = _LEAD.sub("", body, count=1).strip()
    body = _FORMAT_LEAD.sub("", body, count=1).strip()
    body = _INTRO.sub("", body, count=1).strip()
    stripped = _COUNT_LEAD.sub("", body, count=1).strip()
    if stripped:
        body = stripped
    body = re.sub(r"(?:一下|一遍|一点|下)$", "", body).strip()
    body = _TAIL.sub("", body).strip(" ，,。")
    head = re.split(r"[，,；;]", body, maxsplit=1)[0].strip()
    if len(head) >= 4:
        body = head
    if not body:
        body = text.strip()
    if len(body) > 30:
        body = body[:30] + "…"
    return body or "这件事"


def _score(text: str, prof: Profile) -> int:
    low = text.lower()
    hits = sum(1 for kw in prof.keywords if kw in low)
    strong = sum(3 for kw in prof.strong if kw in low)
    return hits + strong


_CHANNEL_BONUS = {
    "邮件": {"email": 4},
    "PPT": {"summary": 2, "plan": 2},
    "周报": {"summary": 4},
    "小红书": {"copy": 4},
    "公众号": {"copy": 4},
    "朋友圈": {"copy": 4},
    "短视频口播": {"copy": 4},
    "电商详情页": {"copy": 3},
    "知乎": {"copy": 2, "explain": 2},
}


def analyze(text: str, parsed: slotlib.Slots | None = None) -> Profile:
    """按关键词命中挑一个意图档；全不命中走通用档。

    "评审/审查" 类词优先于对象词 —— 「评审这段代码」要的是评审档而不是写代码档。
    命中渠道时给对应档加分，「做一份 PPT 汇报」不会被当成写邮件。
    """
    low = text.lower()
    if any(k in low for k in _RECORD_WORDS) and not any(k in low for k in _TRANSLATE_WORDS):
        return _by_key("summary")
    if any(k in low for k in _REVIEW_WORDS):
        return _by_key("review")
    sl = parsed or slotlib.parse(text)
    bonus = _CHANNEL_BONUS.get(sl.channel.name, {}) if sl.channel else {}
    best: Profile | None = None
    best_score = 0
    for prof in PROFILES:
        s = _score(low, prof) + bonus.get(prof.key, 0)
        if s > best_score:
            best, best_score = prof, s
    return best or _GENERIC


_REVIEW_WORDS = ("评审", "审查", "review", "走查", "挑毛病", "找问题")
# 「整理评审会纪要」要的是纪要档，不是评审档
_RECORD_WORDS = ("纪要", "会议记录", "整理", "总结", "归纳", "摘录", "复盘")
_TRANSLATE_WORDS = ("翻译", "润色", "校对", "中译英", "英译中")


def _by_key(key: str) -> Profile:
    for prof in PROFILES:
        if prof.key == key:
            return prof
    return _GENERIC


def _hints(text: str) -> dict:
    low = text.lower()
    out: dict = {}
    for value, keys in _TONE_HINTS:
        if any(k in low for k in keys):
            out["tone"] = value
            break
    for value, keys in _LENGTH_HINTS:
        if any(k in low for k in keys):
            out["length"] = value
            break
    for value, keys in _LANG_HINTS:
        if any(k in low for k in keys):
            out["language"] = value
            break
    extra: list[str] = []
    for style, keys in _PLATFORM_STYLES:
        if any(k in low for k in keys) and style not in extra:
            extra.append(style)
    if extra:
        out["styles"] = extra
    return out


# ----------------------------------------------------------------------- expand


@dataclass
class FillResult:
    spec: PromptSpec
    filled: list[str]
    slots: slotlib.Slots = slotlib.Slots()

    @property
    def changed(self) -> bool:
        return bool(self.filled)

    @property
    def summary(self) -> str:
        return self.slots.summary()


_DEEP_SUCCESS = (
    "指出一处你自己不确定的地方，并说明为什么不确定",
    "点出一个常见但错误的做法，说明错在哪",
)
_DEEP_STEP = ("对着验收标准自查", "逐条回答是否满足，不满足的说明差在哪、怎么补。")

_AUD_TAIL = (
    (("老板", "领导", "总经理", "ceo", "管理层", "总监", "决策"), "，时间稀缺，只看结论和要不要他拍板"),
    (("客户", "甲方", "采购", "供应商", "合作方"), "，关心交期、责任边界和对他有什么影响，不关心内部过程"),
    (("新员工", "新人", "实习生", "小白", "外行"), "，没有上下文，术语第一次出现要解释"),
    (("团队", "同事", "执行", "运营", "部门"), "，是具体做事的人，每条动作都要能直接照着做"),
)


def _merge(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    out = list(base)
    for item in extra:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _slot_success(sl: slotlib.Slots) -> list[str]:
    """由读到的事实推出的验收判据 —— 读不到就不写，不硬编。"""
    out: list[str] = []
    if sl.deadline:
        if 0 < sl.days <= 5:
            out.append(f"在「{sl.deadline}」交付：先给能跑通的最小版本，再补边界处理")
        elif sl.days > 5:
            out.append(f"按「{sl.deadline}」倒排到周，每个阶段写确切日期，不写「尽快」「之后」")
        else:
            out.append(f"「{sl.deadline}」前必须发出，倒推着排，留出对方回复的时间")
    if sl.count_phrase:
        out.append(f"给出 {sl.count_phrase}，各自标注角度和适用场景，结尾一句说明你推荐哪个")
    if sl.audience:
        out.append(f"按「{sl.audience}」的认知水平措辞，不解释他们本来就知道的东西")
    if sl.tech:
        out.append(f"示例统一用 {' / '.join(sl.tech)}，不混用其它语言或框架")
    if sl.emphasis:
        out.append(f"「{sl.emphasis[0]}」单独成段说透，不能一句带过")
    if sl.pages:
        out.append(f"总量控制在 {sl.pages} 页内，超了就砍内容，不靠缩字号塞")
    return out


# 渠道惯例已经覆盖的主题，profile 里同主题的泛化描述就不必再出现
_TOPICS = (
    "标题", "开头", "结尾", "正文", "封面", "主题行",
    "形容词", "空话", "长句", "前两行", "铺垫", "细节", "不相关",
)


def _drop_overlap(base: list[str], channel_text: str) -> list[str]:
    return [s for s in base if not any(t in s and t in channel_text for t in _TOPICS)]


def _slot_must(sl: slotlib.Slots) -> list[str]:
    out: list[str] = []
    if sl.count_phrase:
        out.append(f"{sl.count_phrase}的横向对比")
    if sl.tech:
        out.append(f"在 {' / '.join(sl.tech)} 下跑通，注明依赖版本")
    if sl.emphasis:
        out.append(sl.emphasis[0])
    if sl.pages:
        out.append(f"总页数 ≤ {sl.pages}")
    if sl.channel:
        out.extend(sl.channel.must)
    return out


def _slot_avoid(sl: slotlib.Slots) -> list[str]:
    out = list(sl.forbid)
    if sl.channel:
        out.extend(sl.channel.avoid)
    return out


def _background(prof: Profile, sl: slotlib.Slots, subject: str) -> str:
    text = _fmt(prof.background, subject, sl).rstrip("。")
    extra: list[str] = []
    if sl.deadline:
        extra.append(f"时间上只有「{sl.deadline}」，没有返工余地")
    if sl.channel and sl.channel.name not in text:
        extra.append(f"最终发在{sl.channel.name}，要守那边的惯例")
    if sl.tech:
        extra.append(f"技术环境是 {' / '.join(sl.tech)}")
    if extra:
        text += "；" + "，".join(extra)
    return text + "。"


def _fmt(text: str, subject: str, sl: slotlib.Slots) -> str:
    """把模板里已知的槽位换掉；不知道的给一个中性说法，绝不留下裸花括号。"""
    return (
        text.replace("{subject}", subject)
        .replace("{deadline}", sl.deadline or "既定工期")
        .replace("{count}", sl.count_phrase or "方案")
    )


def _audience_text(prof: Profile, sl: slotlib.Slots, subject: str) -> str:
    if not sl.audience:
        return prof.audience.format(subject=subject)
    low = sl.audience.lower()
    for keys, tail in _AUD_TAIL:
        if any(k in low for k in keys):
            return sl.audience + tail
    return sl.audience


_ANTI_FILLER = (
    "通篇没有具体数字或事实，只有形容词",
    "读完不知道下一步该做什么",
    "把所有选项都列出来，但不给结论",
)


def _anti_example(prof: Profile, sl: slotlib.Slots) -> Example:
    items = _merge(_slot_avoid(sl) or list(prof.avoid), list(_ANTI_FILLER))[:4]
    return Example(
        "反例 · 出现任意两条就重写",
        "（同一份输入）",
        "\n".join(f"· {i}" for i in items),
    )


def expand(spec: PromptSpec, depth: str = DEPTH_STANDARD) -> FillResult:
    """只补空白栏位：已有内容原样保留。task 为空时直接返回未改动副本。

    depth: quick 只给骨架；standard 补全并带上从需求读到的约束；
    deep 额外压反例、成型范例与自查步骤。
    """
    out = PromptSpec.from_dict(spec.to_dict())
    seed = spec.task.strip()
    if not seed:
        return FillResult(out, [], slotlib.Slots())

    sl = slotlib.parse(seed)
    prof = analyze(seed, sl)
    hints = _hints(seed)
    subject = extract_subject(seed)
    filled: list[str] = []
    full = depth != DEPTH_QUICK

    def put(attr: str, value: str, label: str) -> None:
        if not getattr(out, attr).strip() and value.strip():
            setattr(out, attr, value)
            filled.append(label)

    put("role", prof.role, "角色")
    put("background", _background(prof, sl, subject), "背景")
    put("audience", _audience_text(prof, sl, subject), "读者")

    if full:
        if sl.channel:
            # 渠道惯例比通用描述具体得多，让它先上，同主题的通用条目让位
            base = _drop_overlap(list(prof.success), "".join(sl.channel.always))
            succ = _merge(list(sl.channel.always), base)
        else:
            succ = list(prof.success)
        succ = _merge(succ, _slot_success(sl))
        if depth == DEPTH_DEEP:
            succ = _merge(succ, list(_DEEP_SUCCESS))
        put("success", "\n".join(succ[:7 if depth == DEPTH_DEEP else 6]), "成功标准")

        must = _merge(list(prof.must_have), _slot_must(sl))
        put("must_have", "\n".join(must[:5]), "必须包含")

        avoid_base = list(prof.avoid)
        if sl.channel:
            avoid_base = _drop_overlap(avoid_base, "".join(sl.channel.avoid))
        # 用户明确说了「不要…」和渠道硬性禁忌优先，通用条目往后排
        avoid = _merge(_slot_avoid(sl), avoid_base)
        put("avoid", "\n".join(avoid[:5]), "禁止项")
        put("out_schema", prof.schema, "结构要求")

    tone = hints.get("tone") or prof.tone
    if not out.tone and tone in TONE_OPTIONS:
        out.tone = tone
        filled.append("语气")

    if not out.styles:
        # 渠道惯例里的风格比档位默认值更贴，有渠道就听渠道的
        base_styles = list(sl.channel.styles) if (sl.channel and sl.channel.styles) else list(prof.styles)
        styles = _merge(base_styles, hints.get("styles", []))
        styles = [s for s in styles if s in STYLE_OPTIONS][:3]
        if styles:
            out.styles = styles
            filled.append("风格")

    length = hints.get("length") or sl.detail or (sl.channel.length if sl.channel else "") or prof.length
    if out.length == LENGTHS[1] and length != LENGTHS[1]:
        out.length = length
        filled.append("篇幅")

    language = hints.get("language")
    if language and out.language == LANGUAGES[0]:
        out.language = language
        filled.append("语言")

    if out.out_format == OUT_FORMATS[0] and prof.fmt != OUT_FORMATS[0]:
        out.out_format = prof.fmt
        filled.append("输出格式")

    if out.exec_mode == EXEC_MODES[1] and prof.exec_mode != EXEC_MODES[1]:
        out.exec_mode = prof.exec_mode
        filled.append("执行方式")

    if full and not out.filled_examples:
        demo = prof.deep_demo if (depth == DEPTH_DEEP and prof.deep_demo) else prof.demo
        out.examples = [
            Example(
                demo[0],
                _fmt(demo[1], subject, sl),
                _fmt(demo[2], subject, sl),
            )
        ]
        if depth == DEPTH_DEEP:
            out.examples.append(_anti_example(prof, sl))
        filled.append("成型范例 + 反例" if depth == DEPTH_DEEP else "范例骨架")

    if full and not out.filled_steps and prof.steps and (prof.complex_task or len(seed) >= 12):
        steps = [(_fmt(t, subject, sl), _fmt(d, subject, sl)) for t, d in prof.steps]
        if depth == DEPTH_DEEP:
            steps.append(_DEEP_STEP)
        out.steps = [StepItem(t, d) for t, d in steps]
        filled.append(f"{len(out.steps)} 步拆解")

    return FillResult(out, filled, sl)


def profile_label(spec: PromptSpec) -> str:
    """给 UI 用：当前 task 命中哪个意图档。"""
    seed = spec.task.strip()
    if not seed:
        return ""
    prof = analyze(seed)
    return prof.label
