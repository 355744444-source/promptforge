"""Main window for PromptForge."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .autofill import DEPTH_STANDARD, DEPTHS, expand as expand_spec
from .slots import parse as parse_slots
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
from .prompts import TEMPLATES, evaluate, render_prompt, score_label, template_spec
from .theme import APP_EN, APP_NAME, APP_VERSION, COL, PUBLISHER, STEPS, qss
from .widgets import (
    Card,
    ChipGroup,
    FlowLayout,
    NavItem,
    PreviewHighlighter,
    ScoreRing,
    clear_layout,
    field,
    line_input,
    make_button,
    text_area,
)

STEP_META = [
    "角色定分寸，背景定质量。这一步写具体了，后面几步才不用反复返工。",
    "同一个任务，「权威笃定」和「亲切自然」会产出完全不同的结果。别让 AI 自己挑。",
    "范例是最高效的约束——AI 会照着例子对齐格式、颗粒度和用词，比形容词管用十倍。",
    "一次做完的事容易漏后半段。拆成 3–5 步，先做什么、给什么、怎么收口都写清楚。",
    "格式、必须包含、绝对不能出现，三句话说清，能省掉一整轮返工。",
]

EMPTY_PREVIEW = "还没有内容。\n\n在左侧任意步骤填一点东西，这里会实时生成可直接复制的提示词。"


class TemplateCard(QFrame):
    """A clickable template row."""

    def __init__(self, name: str, tag: str, desc: str, on_pick, parent=None):
        super().__init__(parent)
        self.setObjectName("TemplateCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self._on_pick = on_pick

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 11, 14, 12)
        v.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel(name)
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COL['text']};")
        chip = QLabel(tag)
        chip.setStyleSheet(
            f"font-size: 11px; color: {COL['accent_hover']}; background: {COL['accent_soft']};"
            "border-radius: 9px; padding: 2px 9px;"
        )
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(chip)
        v.addLayout(row)

        sub = QLabel(desc)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 12px; color: {COL['muted']};")
        v.addWidget(sub)

        for label in (title, chip, sub):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_pick()


class TemplateDialog(QDialog):
    """Pick a starter template."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("从模板开始")
        self.setMinimumSize(640, 560)
        self.picked = -1

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)

        title = QLabel("选一个起点")
        title.setObjectName("H1")
        v.addWidget(title)

        desc = QLabel("模板只是脚手架，套用之后按你的实际情况改写每一栏。")
        desc.setObjectName("Sub")
        v.addWidget(desc)
        v.addSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host_v = QVBoxLayout(host)
        host_v.setContentsMargins(0, 0, 8, 0)
        host_v.setSpacing(8)

        for i, tpl in enumerate(TEMPLATES):
            card = TemplateCard(
                tpl["name"], tpl["tag"], tpl["desc"], lambda i=i: self._pick(i)
            )
            host_v.addWidget(card)
        host_v.addStretch(1)
        scroll.setWidget(host)
        v.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = make_button("取消", "Ghost")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        v.addLayout(bottom)

    def _pick(self, index: int) -> None:
        self.picked = index
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.spec = PromptSpec()
        self._dirty = False
        self.depth = DEPTH_STANDARD
        self._depth_names = {key: name for key, name in DEPTHS}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._refresh)

        self.setWindowTitle(f"{APP_NAME} {APP_EN} v{APP_VERSION}")
        self.setStyleSheet(qss())
        self._fit_screen()
        self._build()
        self._reload_pages()
        self._goto(0)
        self._refresh()

        QShortcut(QKeySequence.Save, self, self._save_markdown)
        QShortcut(QKeySequence.Open, self, self._open_project)
        QShortcut(QKeySequence.New, self, self._new_spec)

    # ------------------------------------------------------------------ setup
    def _fit_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is None:
            self.resize(1280, 820)
            return
        w = min(1720, int(avail.width() * 0.88))
        h = min(1000, int(avail.height() * 0.90))
        self.resize(w, h)
        self.move(avail.x() + (avail.width() - w) // 2, avail.y() + max(0, (avail.height() - h) // 2))
        self.setMinimumSize(min(1020, avail.width() - 24), min(620, avail.height() - 40))

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_sidebar())
        lay.addWidget(self._build_center(), 1)
        lay.addWidget(self._build_preview())
        self.setCentralWidget(root)

    # --------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(228)

        v = QVBoxLayout(side)
        v.setContentsMargins(14, 16, 14, 14)
        v.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel("P")
        logo.setObjectName("Logo")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        brand.addWidget(logo)

        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(APP_NAME)
        name.setObjectName("Brand")
        ver = QLabel(f"{APP_EN} v{APP_VERSION}")
        ver.setObjectName("BrandSub")
        col.addWidget(name)
        col.addWidget(ver)
        brand.addLayout(col, 1)
        v.addLayout(brand)
        v.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[NavItem] = []
        for i, (num, title, sub) in enumerate(STEPS):
            item = NavItem(num, title, sub)
            item.clicked.connect(lambda _=False, i=i: self._goto(i))
            self.nav_group.addButton(item, i)
            self.nav_buttons.append(item)
            v.addWidget(item)
            v.addSpacing(4)

        v.addStretch(1)

        tpl_btn = make_button("模板库", "Soft")
        tpl_btn.setFixedHeight(36)
        tpl_btn.clicked.connect(self._open_templates)
        v.addWidget(tpl_btn)
        v.addSpacing(8)

        new_btn = make_button("清空重写", "Ghost")
        new_btn.setFixedHeight(34)
        new_btn.clicked.connect(self._new_spec)
        v.addWidget(new_btn)
        v.addSpacing(14)

        pub = QLabel(PUBLISHER)
        pub.setObjectName("Publisher")
        pub.setWordWrap(True)
        v.addWidget(pub)
        return side

    # ---------------------------------------------------------------- center
    def _build_center(self) -> QWidget:
        center = QWidget()
        v = QVBoxLayout(center)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QWidget()
        hv = QVBoxLayout(header)
        hv.setContentsMargins(26, 20, 26, 10)
        hv.setSpacing(6)

        top = QHBoxLayout()
        self.h1 = QLabel()
        self.h1.setObjectName("H1")
        top.addWidget(self.h1)
        top.addStretch(1)
        self.step_badge = QLabel()
        self.step_badge.setObjectName("StepBadge")
        top.addWidget(self.step_badge, 0, Qt.AlignTop)
        hv.addLayout(top)

        self.sub = QLabel()
        self.sub.setObjectName("Sub")
        self.sub.setWordWrap(True)
        hv.addWidget(self.sub)
        v.addWidget(header)

        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)

        footer = QWidget()
        fv = QHBoxLayout(footer)
        fv.setContentsMargins(26, 10, 26, 16)
        fv.setSpacing(10)
        self.prev_btn = make_button("← 上一步", "Ghost")
        self.prev_btn.setFixedHeight(36)
        self.prev_btn.clicked.connect(lambda: self._goto(self.stack.currentIndex() - 1))
        self.next_btn = make_button("下一步 →", "Primary")
        self.next_btn.setFixedHeight(36)
        self.next_btn.clicked.connect(lambda: self._goto(self.stack.currentIndex() + 1))
        fv.addWidget(self.prev_btn)
        fv.addStretch(1)
        fv.addWidget(self.next_btn)
        v.addWidget(footer)
        return center

    # --------------------------------------------------------------- preview
    def _build_preview(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PreviewPanel")
        panel.setFixedWidth(384)
        self.preview_panel = panel

        v = QVBoxLayout(panel)
        v.setContentsMargins(18, 18, 18, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel("实时预览")
        t.setObjectName("CardTitle")
        head.addWidget(t)
        head.addStretch(1)
        self.counter = QLabel("")
        self.counter.setObjectName("Hint")
        head.addWidget(self.counter)
        v.addLayout(head)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("Preview")
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.preview_hl = PreviewHighlighter(self.preview.document())
        v.addWidget(self.preview, 1)

        score_card = QFrame()
        score_card.setObjectName("Card")
        sv = QVBoxLayout(score_card)
        sv.setContentsMargins(14, 12, 14, 14)
        sv.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.ring = ScoreRing(64)
        row.addWidget(self.ring)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.addStretch(1)
        self.score_title = QLabel("提示词完整度")
        self.score_title.setObjectName("FieldLabel")
        self.score_status = QLabel("")
        self.score_status.setObjectName("Sub")
        info.addWidget(self.score_title)
        info.addWidget(self.score_status)
        info.addStretch(1)
        row.addLayout(info, 1)
        sv.addLayout(row)

        self.tips = QLabel("")
        self.tips.setObjectName("Tip")
        self.tips.setWordWrap(True)
        sv.addWidget(self.tips)
        v.addWidget(score_card)

        copy_btn = make_button("复制提示词", "Primary")
        copy_btn.setFixedHeight(38)
        copy_btn.clicked.connect(self._copy)
        v.addWidget(copy_btn)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        b1 = make_button("存为 .md", "Ghost")
        b1.clicked.connect(self._save_markdown)
        b2 = make_button("保存工程", "Ghost")
        b2.clicked.connect(self._save_project)
        b3 = make_button("打开工程", "Ghost")
        b3.clicked.connect(self._open_project)
        for b in (b1, b2, b3):
            b.setFixedHeight(32)
            b.setStyleSheet("font-size: 12px; padding: 4px 6px;")
            tools.addWidget(b)
        v.addLayout(tools)

        self.toast = QLabel("", panel)
        self.toast.setStyleSheet(
            "background: #1F2430; color: #FFFFFF; border-radius: 8px;"
            "padding: 6px 12px; font-size: 12px;"
        )
        self.toast.hide()
        return panel

    # ----------------------------------------------------------------- pages
    def _page_container(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 4, 26, 24)
        v.setSpacing(14)
        return page, v

    def _scroll(self, page: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(page)
        return sa

    def _reload_pages(self) -> None:
        index = self.stack.currentIndex() if self.stack.count() else 0
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        for builder in (self._page_brief, self._page_tone, self._page_examples, self._page_steps, self._page_output):
            self.stack.addWidget(self._scroll(builder()))
        self.stack.setCurrentIndex(max(0, index))

    # helpers bound to the model
    def _set(self, attr: str, value) -> None:
        setattr(self.spec, attr, value)
        self._touch()

    def _line(self, attr: str, placeholder: str = "") -> QLineEdit:
        w = line_input(placeholder)
        w.setText(getattr(self.spec, attr))
        w.textChanged.connect(lambda t, a=attr: self._set(a, t))
        return w

    def _text(self, attr: str, lines: int, placeholder: str = "") -> QPlainTextEdit:
        w = text_area(placeholder, lines)
        w.setPlainText(getattr(self.spec, attr))
        w.textChanged.connect(lambda w=w, a=attr: self._set(a, w.toPlainText()))
        return w

    # page 1 ---------------------------------------------------------------
    def _autofill_row(self) -> QWidget:
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 2, 0, 0)
        v.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(10)
        btn = make_button("按这句话补全后面几栏", "Soft")
        btn.setFixedHeight(34)
        btn.clicked.connect(self._autofill)
        row.addWidget(btn)
        hint = QLabel("只填空白栏，已写的一个字不动。")
        hint.setObjectName("Hint")
        row.addWidget(hint, 1)
        v.addLayout(row)

        depth_row = QHBoxLayout()
        depth_row.setSpacing(8)
        cap = QLabel("补全到")
        cap.setObjectName("Hint")
        depth_row.addWidget(cap)
        self._depth_names = {key: name for key, name in DEPTHS}
        self.depth_chips = ChipGroup(
            [name for _, name in DEPTHS],
            [self._depth_names.get(self.depth, "")],
            multi=False,
            on_change=self._set_depth,
        )
        depth_row.addWidget(self.depth_chips, 1)
        v.addLayout(depth_row)

        self.slot_line = QLabel("")
        self.slot_line.setObjectName("SlotLine")
        self.slot_line.setWordWrap(True)
        v.addWidget(self.slot_line)
        self._update_slots()
        return host

    def _set_depth(self, values) -> None:
        if not values:
            return
        for key, name in DEPTHS:
            if name == values[0]:
                self.depth = key
                break

    def _update_slots(self) -> None:
        line = getattr(self, "slot_line", None)
        if line is None:
            return
        seed = self.spec.task.strip()
        if not seed:
            line.setText("写一句需求，这里会先显示我从话里读到了什么。")
            return
        summary = parse_slots(seed).summary()
        if summary:
            line.setText(f"读到：{summary}")
        else:
            line.setText("没读到硬信息，只能按通用套路补——补上工期、受众或发布渠道会准很多。")

    def _autofill(self) -> None:
        if not self.spec.task.strip():
            self._goto(0)
            self._notify("先在「核心任务」里写一句需求")
            return
        result = expand_spec(self.spec, depth=self.depth)
        if not result.changed:
            self._notify("后面几栏都填好了，没有需要补的")
            return
        self.spec = result.spec
        self._dirty = True
        self._reload_pages()
        self._refresh()
        shown = "、".join(result.filled[:4])
        tail = f" 等 {len(result.filled)} 项" if len(result.filled) > 4 else ""
        self._notify(f"已补全：{shown}{tail}")

    def _page_brief(self) -> QWidget:
        page, v = self._page_container()

        c1 = Card("你是谁，站在什么处境", "角色决定取舍的分寸，背景决定它需不需要猜。")
        c1.add(field("角色设定", self._line("role", "例如：资深后端工程师 / 小红书文案操盘手")))
        c1.add(field("业务背景", self._text("background", 4, "为什么要做这件事？当前现状、已有材料、限制条件…")))
        c1.add(field("目标读者", self._line("audience", "例如：只看结论的总经理 / 25-35 岁上班族")))
        v.addWidget(c1)

        c2 = Card("要它做什么", "一句话说清动作，再补一条能被检查的验收判据。")
        task_box = self._text("task", 3, "对什么对象、做什么动作、达到什么状态")
        task_box.textChanged.connect(self._update_slots)
        c2.add(field("核心任务", task_box))
        c2.add(self._autofill_row())
        c2.add(
            field(
                "成功标准",
                self._text("success", 3, "每行一条，例如：全文不超过 800 字"),
                "写得越像验收单，AI 越不会交一份「看起来还行」的作业。",
            )
        )
        v.addWidget(c2)
        v.addStretch(1)
        return page

    # page 2 ---------------------------------------------------------------
    def _page_tone(self) -> QWidget:
        page, v = self._page_container()

        c1 = Card("语气", "单选。语气决定它对读者说话的方式。")
        c1.add(
            ChipGroup(
                TONE_OPTIONS,
                [self.spec.tone] if self.spec.tone else [],
                multi=False,
                on_change=lambda vals: self._set("tone", vals[0] if vals else ""),
            )
        )
        v.addWidget(c1)

        c2 = Card("风格", "可多选。风格是更外层的表达形态，可以和语气叠加。")
        c2.add(
            ChipGroup(
                STYLE_OPTIONS,
                self.spec.styles,
                multi=True,
                on_change=lambda vals: self._set("styles", list(vals)),
            )
        )
        v.addWidget(c2)

        c3 = Card("语言与篇幅")
        row = QHBoxLayout()
        row.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(6)
        lb = QLabel("输出语言")
        lb.setObjectName("FieldLabel")
        left.addWidget(lb)
        left.addWidget(
            ChipGroup(
                LANGUAGES,
                [self.spec.language],
                multi=False,
                on_change=lambda vals: self._set("language", vals[0] if vals else LANGUAGES[0]),
            )
        )
        right = QVBoxLayout()
        right.setSpacing(6)
        rb = QLabel("篇幅")
        rb.setObjectName("FieldLabel")
        right.addWidget(rb)
        right.addWidget(
            ChipGroup(
                LENGTHS,
                [self.spec.length],
                multi=False,
                on_change=lambda vals: self._set("length", vals[0] if vals else LENGTHS[1]),
            )
        )
        row.addLayout(left, 1)
        row.addLayout(right, 1)
        holder = QWidget()
        holder.setLayout(row)
        c3.add(holder)
        v.addWidget(c3)

        c4 = Card("文风示例", "贴一段你希望它模仿的文字——这是最省事的「语气说明书」。")
        c4.add(self._text("style_sample", 5, "粘贴一段范文，或者写一句你想要的语感示范…"))
        v.addWidget(c4)
        v.addStretch(1)
        return page

    # page 3 ---------------------------------------------------------------
    def _page_examples(self) -> QWidget:
        page, v = self._page_container()
        card = Card(
            "参考范例",
            "AI 会照着例子对齐格式、颗粒度和用词。建议一组正常情况 + 一组边界情况，两组就够。",
        )

        self.ex_host = QWidget()
        self.ex_layout = QVBoxLayout(self.ex_host)
        self.ex_layout.setContentsMargins(0, 0, 0, 0)
        self.ex_layout.setSpacing(10)
        card.add(self.ex_host)

        add = make_button("＋ 添加一组范例", "Ghost")
        add.setFixedHeight(36)
        add.clicked.connect(self._add_example)
        card.add(add, gap=12)
        v.addWidget(card)
        v.addStretch(1)

        self._render_examples()
        return page

    def _render_examples(self) -> None:
        clear_layout(self.ex_layout)
        if not self.spec.examples:
            empty = QLabel("还没有范例。\n有范例时 AI 的输出会稳定得多——哪怕只给一组。")
            empty.setObjectName("Empty")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(78)
            self.ex_layout.addWidget(empty)
            return
        for i, ex in enumerate(self.spec.examples):
            self.ex_layout.addWidget(self._example_card(i, ex))

    def _example_card(self, index: int, ex: Example) -> QWidget:
        box = QFrame()
        box.setObjectName("Inner")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        tag = QLabel(f"范例 {index + 1}")
        tag.setStyleSheet(f"color: {COL['accent_hover']}; font-size: 12px; font-weight: 700;")
        head.addWidget(tag)
        head.addStretch(1)
        up = make_button("↑", "Tiny")
        up.setFixedSize(26, 24)
        up.setEnabled(index > 0)
        up.clicked.connect(lambda _=False, i=index: self._move_example(i, -1))
        down = make_button("↓", "Tiny")
        down.setFixedSize(26, 24)
        down.setEnabled(index < len(self.spec.examples) - 1)
        down.clicked.connect(lambda _=False, i=index: self._move_example(i, 1))
        rm = make_button("删除", "TinyDanger")
        rm.setFixedHeight(24)
        rm.clicked.connect(lambda _=False, i=index: self._remove_example(i))
        head.addWidget(up)
        head.addWidget(down)
        head.addWidget(rm)
        v.addLayout(head)

        title = line_input("标题（可留空），例如：边界输入")
        title.setText(ex.title)
        title.textChanged.connect(lambda t, e=ex: self._edit_example(e, "title", t))
        v.addWidget(field("标题", title))

        inp = text_area("用户给 AI 的原话 / 输入数据…", 3, 16)
        inp.setPlainText(ex.input)
        inp.textChanged.connect(lambda w=inp, e=ex: self._edit_example(e, "input", w.toPlainText()))
        v.addWidget(field("输入", inp))

        out = text_area("你期望 AI 给出的输出…", 3, 16)
        out.setPlainText(ex.output)
        out.textChanged.connect(lambda w=out, e=ex: self._edit_example(e, "output", w.toPlainText()))
        v.addWidget(field("输出", out))
        return box

    def _edit_example(self, ex: Example, attr: str, value: str) -> None:
        setattr(ex, attr, value)
        self._touch()

    def _add_example(self) -> None:
        self.spec.examples.append(Example())
        self._render_examples()
        self._touch()

    def _remove_example(self, index: int) -> None:
        if 0 <= index < len(self.spec.examples):
            self.spec.examples.pop(index)
            self._render_examples()
            self._touch()

    def _move_example(self, index: int, delta: int) -> None:
        items = self.spec.examples
        target = index + delta
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
            self._render_examples()
            self._touch()

    # page 4 ---------------------------------------------------------------
    def _page_steps(self) -> QWidget:
        page, v = self._page_container()

        c1 = Card("执行方式", "决定它是「一口气给完」，还是「先给计划」。")
        c1.add(
            ChipGroup(
                EXEC_MODES,
                [self.spec.exec_mode],
                multi=False,
                on_change=lambda vals: self._set("exec_mode", vals[0] if vals else EXEC_MODES[1]),
            )
        )
        v.addWidget(c1)

        card = Card("步骤拆解", "按「先做什么 → 给什么 → 怎么收口」排。3–5 步最好，超过 7 步就该拆成两次对话。")
        self.st_host = QWidget()
        self.st_layout = QVBoxLayout(self.st_host)
        self.st_layout.setContentsMargins(0, 0, 0, 0)
        self.st_layout.setSpacing(10)
        card.add(self.st_host)

        add = make_button("＋ 添加一步", "Ghost")
        add.setFixedHeight(36)
        add.clicked.connect(self._add_step)
        card.add(add, gap=12)
        v.addWidget(card)
        v.addStretch(1)

        self._render_steps()
        return page

    def _render_steps(self) -> None:
        clear_layout(self.st_layout)
        if not self.spec.steps:
            empty = QLabel("还没有步骤。任务不复杂可以留空；要分步执行时，先加第一步。")
            empty.setObjectName("Empty")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(78)
            self.st_layout.addWidget(empty)
            return
        for i, st in enumerate(self.spec.steps):
            self.st_layout.addWidget(self._step_card(i, st))

    def _step_card(self, index: int, st: StepItem) -> QWidget:
        box = QFrame()
        box.setObjectName("Inner")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        num = QLabel(str(index + 1))
        num.setFixedSize(22, 22)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet(
            f"background: {COL['accent_soft']}; color: {COL['accent_hover']};"
            "border-radius: 11px; font-size: 11px; font-weight: 700;"
        )
        head.addWidget(num)

        title = line_input("这一步做什么，例如：先给方案再写代码")
        title.setText(st.title)
        title.textChanged.connect(lambda t, s=st: self._edit_step(s, "title", t))
        head.addWidget(title, 1)

        up = make_button("↑", "Tiny")
        up.setFixedSize(26, 24)
        up.setEnabled(index > 0)
        up.clicked.connect(lambda _=False, i=index: self._move_step(i, -1))
        down = make_button("↓", "Tiny")
        down.setFixedSize(26, 24)
        down.setEnabled(index < len(self.spec.steps) - 1)
        down.clicked.connect(lambda _=False, i=index: self._move_step(i, 1))
        rm = make_button("✕", "TinyDanger")
        rm.setFixedSize(26, 24)
        rm.clicked.connect(lambda _=False, i=index: self._remove_step(i))
        head.addWidget(up)
        head.addWidget(down)
        head.addWidget(rm)
        v.addLayout(head)

        detail = line_input("补充要求（可留空），例如：说明分批策略与异常处理")
        detail.setText(st.detail)
        detail.textChanged.connect(lambda t, s=st: self._edit_step(s, "detail", t))
        v.addWidget(detail)
        return box

    def _edit_step(self, st: StepItem, attr: str, value: str) -> None:
        setattr(st, attr, value)
        self._touch()

    def _add_step(self) -> None:
        self.spec.steps.append(StepItem())
        self._render_steps()
        self._touch()

    def _remove_step(self, index: int) -> None:
        if 0 <= index < len(self.spec.steps):
            self.spec.steps.pop(index)
            self._render_steps()
            self._touch()

    def _move_step(self, index: int, delta: int) -> None:
        items = self.spec.steps
        target = index + delta
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
            self._render_steps()
            self._touch()

    # page 5 ---------------------------------------------------------------
    def _page_output(self) -> QWidget:
        page, v = self._page_container()

        c1 = Card("输出格式", "选一个你最可能直接拿去用的形态。")
        c1.add(
            ChipGroup(
                OUT_FORMATS,
                [self.spec.out_format],
                multi=False,
                on_change=lambda vals: self._set("out_format", vals[0] if vals else OUT_FORMATS[0]),
            )
        )
        v.addWidget(c1)

        c2 = Card("结构与红线", "这三栏最容易漏，也最能省返工。")
        c2.add(
            field(
                "结构要求",
                self._text("out_schema", 3, "每行一条，例如：先给结论，再给三点理由"),
            )
        )
        c2.add(
            field(
                "必须包含",
                self._text("must_have", 3, "每行一条，例如：每个结论都要附上数据依据"),
            )
        )
        c2.add(
            field(
                "不要出现",
                self._text("avoid", 3, "每行一条，例如：不要用「赋能」「抓手」这类词"),
                "反向约束往往比正向要求更有效——直接点名你不想要的东西。",
            )
        )
        v.addWidget(c2)
        v.addStretch(1)
        return page

    # ------------------------------------------------------------- behaviour
    def _goto(self, index: int) -> None:
        index = max(0, min(len(STEPS) - 1, index))
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.h1.setText(f"{STEPS[index][0]} · {STEPS[index][1]}")
        self.sub.setText(STEP_META[index])
        self.step_badge.setText(f"第 {index + 1} / {len(STEPS)} 步")
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(STEPS) - 1)
        page = self.stack.widget(index)
        if isinstance(page, QScrollArea):
            page.verticalScrollBar().setValue(0)

    def _touch(self) -> None:
        self._dirty = True
        self._timer.start()

    def _refresh(self) -> None:
        text = EMPTY_PREVIEW if self.spec.is_blank() else render_prompt(self.spec)
        bar = self.preview.verticalScrollBar()
        pos = bar.value()
        self.preview.setPlainText(text)
        bar.setValue(min(pos, bar.maximum()))

        self.counter.setText("" if self.spec.is_blank() else f"{len(text)} 字符")

        score, checks, tips = evaluate(self.spec)
        self.ring.set_score(score)
        self.score_status.setText(f"{score_label(score)} · {score} / 100")
        self.tips.setText("\n".join("· " + t for t in tips))

    def _copy(self) -> None:
        if self.spec.is_blank():
            self._notify("还没有内容可复制")
            return
        QGuiApplication.clipboard().setText(render_prompt(self.spec))
        self._notify("已复制到剪贴板")

    def _notify(self, message: str) -> None:
        self.toast.setText(message)
        self.toast.adjustSize()
        x = max(12, (self.preview_panel.width() - self.toast.width()) // 2)
        y = self.preview_panel.height() - self.toast.height() - 64
        self.toast.move(x, y)
        self.toast.show()
        self.toast.raise_()
        QTimer.singleShot(1800, self.toast.hide)

    def _default_dir(self) -> str:
        desktop = Path.home() / "Desktop"
        return str(desktop if desktop.exists() else Path.home())

    def _save_markdown(self) -> None:
        if self.spec.is_blank():
            self._notify("还没有内容可保存")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存提示词", str(Path(self._default_dir()) / "prompt.md"), "Markdown (*.md);;文本 (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(render_prompt(self.spec), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"写入文件时出错：\n{exc}")
            return
        self._dirty = False
        self._notify("已保存到我选择的路径")

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存工程", str(Path(self._default_dir()) / "prompt.pfz"), "提示词工程 (*.pfz);;JSON (*.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self.spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"写入文件时出错：\n{exc}")
            return
        self._dirty = False
        self._notify("工程已保存")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开工程", self._default_dir(), "提示词工程 (*.pfz *.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "打开失败", f"文件无法读取：\n{exc}")
            return
        self.spec = PromptSpec.from_dict(data)
        self._dirty = False
        self._reload_pages()
        self._goto(self.stack.currentIndex())
        self._refresh()
        self._notify("工程已载入")

    def _new_spec(self) -> None:
        if not self.spec.is_blank():
            ans = QMessageBox.question(
                self,
                "清空重写",
                "当前内容会被清空，确定吗？\n（如果还没保存，建议先「保存工程」）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
        self.spec = PromptSpec()
        self._dirty = False
        self._reload_pages()
        self._goto(0)
        self._refresh()
        self._notify("已清空")

    def _apply_template(self, index: int) -> None:
        self.spec = template_spec(index)
        self._dirty = True
        self._reload_pages()
        self._goto(0)
        self._refresh()
        self._notify(f"已套用：{TEMPLATES[index]['name']}")

    def _open_templates(self) -> None:
        if not self.spec.is_blank():
            ans = QMessageBox.question(
                self,
                "套用模板",
                "套用模板会覆盖当前内容，确定吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
        dlg = TemplateDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.picked >= 0:
            self._apply_template(dlg.picked)

    def closeEvent(self, event) -> None:
        if self._dirty and not self.spec.is_blank():
            ans = QMessageBox.question(
                self,
                "退出",
                "还有未保存的修改，确定退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
