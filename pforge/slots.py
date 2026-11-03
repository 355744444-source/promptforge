"""Slot extraction — 从一句需求里读出确定性的信息。

`parse()` 只做抽取，不做判断；`autofill` 拿这些槽位去拼具体内容。
抽不到就不编，宁可留空。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# --------------------------------------------------------------------- numbers
_CN = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十五": 15, "二十": 20, "三十": 30,
}
_NUM = r"(?:\d{1,3}|[一二两三四五六七八九十]{1,3})"


def _num(raw: str) -> int:
    if raw.isdigit():
        return int(raw)
    return _CN.get(raw, 0)


# -------------------------------------------------------------------- deadline
_DUR = re.compile(
    rf"({_NUM})\s*(?:个)?\s*(天|日|周|星期|礼拜)\s*(?:内|之内|以内|之前|前|左右)?"
)
_DUR_M = re.compile(rf"({_NUM})\s*(?:个)?\s*月(?:内|之内|以内|底|之前|前)")
_FIXED = re.compile(
    r"(本月内|月底前|月底|月初|季度末|年底前|年底|年前|年中|下个?季度|"
    r"本季度|Q[1-4]|本周[一二三四五六日天]|下周[一二三四五六日天]|明天|后天|今天)"
)
_UNIT_DAYS = {"天": 1, "日": 1, "周": 7, "星期": 7, "礼拜": 7, "月": 30}


# ---------------------------------------------------------------------- count
# 「3 个方案」算数量要求；「一份文案」只是量词，不算。
# 名词只认白名单里的词，避免把「5 条朋友圈招聘文案」里的“朋友圈”也吃进数量短语。
_COUNT_NOUN = "方案|版本|标题|文案|选项|角度|路径|措辞|说法|思路|建议|稿子|话术|样本|变体|风格"
_COUNT = re.compile(
    rf"({_NUM})\s*(个|条|版|篇|种|套|张|封|组|轮|档|支|集)\s*((?:{_COUNT_NOUN}){{0,2}})"
)


# -------------------------------------------------------------------- channel
@dataclass(frozen=True)
class Channel:
    """一个发布渠道的硬性惯例——写进成功标准才管用。"""

    name: str
    styles: tuple[str, ...] = ()
    length: str = ""
    always: tuple[str, ...] = ()
    must: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


CHANNELS: tuple[Channel, ...] = (
    Channel(
        "小红书",
        styles=("口语化", "故事化"),
        length="精简",
        always=(
            "标题 ≤20 字，且至少含 1 个具体数字或一组对比",
            "第一句就给出继续读的理由，不做背景铺垫",
            "结尾落到一个具体动作，并带 3–5 个话题标签",
        ),
        must=("3–5 个话题标签", "一句能被截图转发的金句"),
        avoid=("书面化长句", "「品质之选」这类形容词堆砌", "「最 / 第一 / 绝对」等违禁词"),
    ),
    Channel(
        "公众号",
        styles=("故事化", "书面正式"),
        always=(
            "前 200 字内给出钩子，交代读者为什么要往下读",
            "每 3–4 段一个小标题，扫读也能看懂主线",
        ),
        must=("小标题", "结尾的引导动作"),
        avoid=("开头铺陈背景超过 200 字", "连续 5 段以上不分段"),
    ),
    Channel(
        "短视频口播",
        styles=("口语化",),
        length="精简",
        always=(
            "前 3 秒抛出冲突或反常识，不留寒暄",
            "一句一行，按口播节奏断句",
            "按 60–90 秒估时，全文控制在 200–260 字",
        ),
        must=("开头 3 秒的钩子", "可念出口的短句"),
        avoid=("长定语从句", "「因此 / 综上」这类书面连接词"),
    ),
    Channel(
        "邮件",
        styles=("书面正式",),
        length="精简",
        always=(
            "主题行 20 字内同时含动作与截止时间",
            "前两行给结论，细节全部放在后面",
            "结尾只留一个明确的下一步",
        ),
        must=("主题行", "明确的下一步与时间"),
        avoid=("三段以上的铺垫", "一封邮件讲两件不相关的事"),
    ),
    Channel(
        "周报",
        styles=("清单体",),
        always=(
            "按「结论 → 关键进展（带数字）→ 风险与卡点 → 下周计划」组织",
            "每条进展给出数字或前后对比，不用「基本完成」「推进中」",
        ),
        must=("每条进展的数字或对比", "风险点以及需要谁支持"),
        avoid=("流水账式罗列任务", "没有数字的形容词"),
    ),
    Channel(
        "PPT",
        styles=("清单体",),
        always=(
            "一页只讲一个结论，标题写成判断句而不是名词短语",
            "每页正文不超过 5 行，其余内容放进备注",
        ),
        must=("每页的判断句标题", "一页一个结论"),
        avoid=("整页大段文字", "只写「项目进展」这类名词标题"),
    ),
    Channel(
        "电商详情页",
        always=(
            "首屏把最大的一个利益点说清，参数往后放",
            "每个参数都翻译成用户能感知的结果，而不是只列数字",
        ),
        must=("参数到利益的转换", "售后或保障说明"),
        avoid=("只堆参数不解释", "「最 / 第一 / 100%」等绝对化用语"),
    ),
    Channel(
        "朋友圈",
        styles=("口语化",),
        length="精简",
        always=("控制在 60 字内，第一人称", "只说清一个点，不列条目"),
        avoid=("超过 3 行的长段", "群发感的模板句"),
    ),
    Channel(
        "知乎",
        styles=("书面正式",),
        always=("开头先给结论，再展开论证", "每个论点配一个具体例子或数据"),
        must=("结论前置", "至少一个具体例证"),
        avoid=("只讲道理不给例子", "情绪化表达替代理据"),
    ),
)

_CHANNEL_ALIASES = (
    ("小红书", ("小红书", "红书", "笔记")),
    ("公众号", ("公众号", "推文", "订阅号")),
    ("短视频口播", ("抖音", "快手", "短视频", "口播", "视频号", "b站视频")),
    ("邮件", ("邮件", "email", "mail", "回信")),
    ("周报", ("周报", "月报", "日报")),
    ("PPT", ("ppt", "幻灯片", "演示文稿", "汇报材料")),
    ("电商详情页", ("详情页", "商品页", "电商", "主图", "listing")),
    ("朋友圈", ("朋友圈",)),
    ("知乎", ("知乎", "长文")),
)


# ------------------------------------------------------------------- audience
_AUD = re.compile(
    r"(?:^|[，,。；;\s]|帮我|请)?(?:给|面向|向|对|帮|替)\s*"
    r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?)\s*"
    r"(?:写|做|发|看|用|汇报|介绍|讲|输出|整理|评审|回|问|转|出|生成)"
)
_AUD_STOP = {"他们", "大家", "自己", "别人", "我们", "你们"}


# ---------------------------------------------------------------------- other
_TECH = (
    "python", "java", "javascript", "typescript", "c++", "c#", "golang",
    "rust", "vue", "react", "qt", "sql", "excel", "shell", "bash",
    "docker", "pytorch", "opencv",
)
_TECH_PAT = {
    t: re.compile(rf"(?<![a-z0-9+#]){re.escape(t)}(?![a-z0-9+#])")
    for t in _TECH
}

# 「别」在「特别 / 区别 / 级别 / 分别 / 识别 / 类别」里不是否定词
_FORBID = re.compile(
    r"(?:不要|不许|避免|不能|千万别|切忌|(?<![特区级分性识类告])别)\s*([^，,。；;\n]{2,20})"
)
_EMPH = re.compile(
    r"(?:重点|突出|强调|一定要|必须|务必|核心是|特别是|特别注意)\s*([^，,。；;\n]{2,20})"
)
_PAGES = re.compile(rf"(?:控制在|不超过|最多|限)\s*({_NUM})\s*页|({_NUM})\s*页(?:以内|内|左右)")

_DETAIL_DEEP = ("详细", "详尽", "全面", "深度", "展开", "细致", "长一点", "细一点")
_DETAIL_SHORT = ("精简", "简短", "短一点", "别太长", "控制在", "几句话")


# ---------------------------------------------------------------------- Slots
@dataclass(frozen=True)
class Slots:
    """一句话里被确认读到的信息。没读到就是空，不猜。"""

    subject: str = ""
    deadline: str = ""
    days: int = 0
    count: int = 0
    count_phrase: str = ""
    pages: int = 0
    channel: Channel | None = None
    audience: str = ""
    tech: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    emphasis: tuple[str, ...] = ()
    detail: str = ""

    def labels(self) -> list[str]:
        """给界面用的一行摘要。"""
        out: list[str] = []
        if self.deadline:
            out.append(self.deadline)
        if self.count_phrase:
            out.append(self.count_phrase)
        if self.pages:
            out.append(f"{self.pages} 页")
        if self.channel:
            out.append(self.channel.name)
        if self.audience:
            out.append(f"读者 {self.audience}")
        if self.tech:
            out.append(" / ".join(self.tech))
        if self.emphasis:
            out.append("重点 " + self.emphasis[0])
        if self.forbid:
            out.append("不写 " + self.forbid[0])
        return out

    def summary(self) -> str:
        labels = self.labels()
        return " · ".join(labels) if labels else ""


def parse(text: str) -> Slots:
    low = text.lower()

    deadline, days = _deadline(text)
    count, phrase = _count(text)
    channel = _channel(low)
    audience = _audience(text)
    tech = tuple(t for t in _TECH if _TECH_PAT[t].search(low))

    return Slots(
        deadline=deadline,
        days=days,
        count=count,
        count_phrase=phrase,
        pages=_pages(text),
        channel=channel,
        audience=audience,
        tech=tech,
        forbid=_matches(_FORBID, text)[:2],
        emphasis=_matches(_EMPH, text)[:2],
        detail=_detail(low),
    )


def _pages(text: str) -> int:
    m = _PAGES.search(text)
    if not m:
        return 0
    return _num(m.group(1) or m.group(2) or "")


def _matches(pat: re.Pattern, text: str) -> tuple[str, ...]:
    found: list[str] = []
    for m in pat.finditer(text):
        v = m.group(1).strip()
        if v and v not in found:
            found.append(v)
    return tuple(found)


def _deadline(text: str) -> tuple[str, int]:
    m = _DUR.search(text)
    if m:
        n = _num(m.group(1))
        unit = "天" if m.group(2) == "日" else m.group(2)
        if n:
            return m.group(0).strip(), n * _UNIT_DAYS.get(unit, 1)
    m = _DUR_M.search(text)
    if m:
        n = _num(m.group(1))
        if n:
            return m.group(0).strip(), n * 30
    m = _FIXED.search(text)
    if m:
        return m.group(1), 0
    return "", 0


def _count(text: str) -> tuple[int, str]:
    for m in _COUNT.finditer(text):
        n = _num(m.group(1))
        # 1 个 / 一份 是量词，不是「要几份」
        if n >= 2:
            phrase = f"{n} {m.group(2)}{m.group(3)}".strip()
            return n, phrase
    return 0, ""


def _channel(low: str) -> Channel | None:
    # 长别名优先：「ppt」要压过别的词，别名越长越具体
    for alias, ch in _CHANNEL_LOOKUP:
        if alias in low:
            return ch
    return None


_CHANNEL_LOOKUP = sorted(
    ((alias, ch) for ch in CHANNELS for alias in dict(_CHANNEL_ALIASES)[ch.name]),
    key=lambda pair: -len(pair[0]),
)


def _audience(text: str) -> str:
    for m in _AUD.finditer(text):
        v = m.group(1).strip()
        if v in _AUD_STOP or len(v) < 2:
            continue
        return v
    return ""


def _detail(low: str) -> str:
    if any(k in low for k in _DETAIL_DEEP):
        return "详细"
    if any(k in low for k in _DETAIL_SHORT):
        return "精简"
    return ""
