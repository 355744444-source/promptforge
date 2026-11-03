"""Data model for a prompt specification (serialisable to .pfz project files)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PROJECT_FORMAT = "promptforge/1"

LANGUAGES = ["简体中文", "繁体中文", "English", "中英双语"]
LENGTHS = ["精简", "适中", "详尽"]
EXEC_MODES = ["一次性输出", "先给计划，再执行", "分步确认"]
OUT_FORMATS = ["Markdown", "纯文本", "表格", "JSON", "代码块", "分点清单"]
TONE_OPTIONS = ["专业严谨", "简洁直接", "亲切自然", "幽默风趣", "权威笃定", "温柔鼓励"]
STYLE_OPTIONS = ["书面正式", "口语化", "故事化", "清单体", "学术中立", "犀利直接"]


def _s(v) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


@dataclass
class Example:
    title: str = ""
    input: str = ""
    output: str = ""

    @property
    def filled(self) -> bool:
        return bool(self.input.strip() or self.output.strip())


@dataclass
class StepItem:
    title: str = ""
    detail: str = ""

    @property
    def filled(self) -> bool:
        return bool(self.title.strip())


@dataclass
class PromptSpec:
    # 1. 任务与背景
    role: str = ""
    background: str = ""
    audience: str = ""
    task: str = ""
    success: str = ""
    # 2. 语气与风格
    tone: str = ""
    styles: list[str] = field(default_factory=list)
    language: str = LANGUAGES[0]
    length: str = LENGTHS[1]
    style_sample: str = ""
    # 3. 参考范例
    examples: list[Example] = field(default_factory=list)
    # 4. 复杂任务拆解
    steps: list[StepItem] = field(default_factory=list)
    exec_mode: str = EXEC_MODES[1]
    # 5. 输出要求
    out_format: str = OUT_FORMATS[0]
    out_schema: str = ""
    must_have: str = ""
    avoid: str = ""

    # -- helpers -------------------------------------------------
    @property
    def filled_examples(self) -> list[Example]:
        return [e for e in self.examples if e.filled]

    @property
    def filled_steps(self) -> list[StepItem]:
        return [s for s in self.steps if s.filled]

    def is_blank(self) -> bool:
        return not any(
            [
                self.role.strip(),
                self.background.strip(),
                self.audience.strip(),
                self.task.strip(),
                self.success.strip(),
                self.style_sample.strip(),
                self.out_schema.strip(),
                self.must_have.strip(),
                self.avoid.strip(),
                self.tone,
                self.styles,
                self.filled_examples,
                self.filled_steps,
            ]
        )

    # -- serialisation -------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = PROJECT_FORMAT
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PromptSpec":
        data = data if isinstance(data, dict) else {}
        spec = cls()
        for name in (
            "role",
            "background",
            "audience",
            "task",
            "success",
            "tone",
            "style_sample",
            "out_schema",
            "must_have",
            "avoid",
        ):
            setattr(spec, name, _s(data.get(name)))
        for name, allowed, default in (
            ("language", LANGUAGES, LANGUAGES[0]),
            ("length", LENGTHS, LENGTHS[1]),
            ("exec_mode", EXEC_MODES, EXEC_MODES[1]),
            ("out_format", OUT_FORMATS, OUT_FORMATS[0]),
        ):
            value = _s(data.get(name)) or default
            setattr(spec, name, value if value in allowed else default)

        styles = data.get("styles")
        if isinstance(styles, list):
            spec.styles = [_s(x) for x in styles if _s(x).strip()]

        examples = data.get("examples")
        spec.examples = []
        if isinstance(examples, list):
            for item in examples:
                if isinstance(item, Example):
                    spec.examples.append(item)
                elif isinstance(item, dict):
                    spec.examples.append(
                        Example(
                            _s(item.get("title")),
                            _s(item.get("input")),
                            _s(item.get("output")),
                        )
                    )

        steps = data.get("steps")
        spec.steps = []
        if isinstance(steps, list):
            for item in steps:
                if isinstance(item, StepItem):
                    spec.steps.append(item)
                elif isinstance(item, dict):
                    spec.steps.append(StepItem(_s(item.get("title")), _s(item.get("detail"))))
        return spec
