"""Headless interaction smoke test: builds the real window and drives it."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from pforge.app import EMPTY_PREVIEW, MainWindow  # noqa: E402
from pforge.prompts import TEMPLATES, evaluate, render_prompt  # noqa: E402
from pforge.theme import app_font  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setFont(app_font())

    win = MainWindow()
    win.show()
    app.processEvents()
    check("window builds", win.stack.count() == 5, f"pages={win.stack.count()}")

    check("blank preview placeholder", win.preview.toPlainText() == EMPTY_PREVIEW)

    # navigate every step
    for i in range(5):
        win._goto(i)
        app.processEvents()
        check(f"goto step {i + 1}", win.stack.currentIndex() == i)

    # typing updates the model and the preview
    win._goto(0)
    app.processEvents()
    edits = win.stack.widget(0).widget().findChildren(QLineEdit)
    check("page 1 has line inputs", len(edits) >= 2, str(len(edits)))
    edits[0].setText("资深数据分析师")
    app.processEvents()
    check("typing writes into spec", win.spec.role == "资深数据分析师", win.spec.role)

    # templates
    win._apply_template(4)
    app.processEvents()
    check("template applied", "周报" in TEMPLATES[4]["name"])
    score, _, _ = evaluate(win.spec)
    check("template scores high", score >= 85, str(score))
    expected = render_prompt(win.spec)
    check("preview matches render", expected.splitlines()[0] in win.preview.toPlainText())

    # clipboard
    win._copy()
    app.processEvents()
    check("copy puts prompt on clipboard", QGuiApplication.clipboard().text() == expected)

    # examples add / remove
    start = len(win.spec.examples)
    win._add_example()
    app.processEvents()
    check("add example", len(win.spec.examples) == start + 1)
    win._remove_example(start)
    app.processEvents()
    check("remove example", len(win.spec.examples) == start)
    win._move_example(0, 1)
    app.processEvents()
    check("move example", win.spec.examples[0].title != "")

    # steps add / move / remove
    win._goto(3)
    app.processEvents()
    n_steps = len(win.spec.steps)
    win._add_step()
    win._edit_step(win.spec.steps[-1], "title", "最后收个尾")
    app.processEvents()
    check("add step", len(win.spec.steps) == n_steps + 1)
    win._move_step(n_steps, -1)
    app.processEvents()
    check("move step", win.spec.steps[n_steps - 1].title == "最后收个尾")
    win._remove_step(n_steps - 1)
    app.processEvents()
    check("remove step", len(win.spec.steps) == n_steps)

    # new / reset
    win.spec = type(win.spec)()
    win._reload_pages()
    win._goto(0)
    win._refresh()
    app.processEvents()
    check("reset to blank", win.preview.toPlainText() == EMPTY_PREVIEW)

    # empty-state rendering of list pages
    win._goto(2)
    app.processEvents()
    win._goto(3)
    app.processEvents()
    check("empty lists render", True)

    # auto-continuation from one sentence
    win._goto(0)
    win.spec.task = "给运营团队写一份双十一活动方案，两周内上线"
    win._reload_pages()
    win._refresh()
    app.processEvents()
    win._autofill()
    app.processEvents()
    check("autofill fills role", win.spec.role == "资深项目经理", win.spec.role)
    check("autofill fills steps", len(win.spec.filled_steps) == 4, str(len(win.spec.filled_steps)))
    check("autofill updates preview", "资深项目经理" in win.preview.toPlainText())
    score, _, _ = evaluate(win.spec)
    check("autofill score jumps", score >= 80, str(score))
    first_steps = [s.title for s in win.spec.filled_steps]
    win._autofill()
    app.processEvents()
    check("second autofill is a no-op", [s.title for s in win.spec.filled_steps] == first_steps)

    # 深度切换：深入档多一步、多一组反例；精简档只给骨架
    seed = "给运营团队写一份双十一活动方案，两周内上线"
    win.spec = type(win.spec)(task=seed)
    win._reload_pages()
    win._refresh()
    app.processEvents()
    check("slot hint shows what was read", "两周内" in win.slot_line.text(), win.slot_line.text())
    win._set_depth(["深入"])
    check("depth switches to deep", win.depth == "deep", win.depth)
    win._autofill()
    app.processEvents()
    check("deep adds one more step", len(win.spec.filled_steps) == 5, str(len(win.spec.filled_steps)))
    check("deep gives two examples", len(win.spec.filled_examples) == 2)
    check("deep example is a worked one", "成型" in win.spec.filled_examples[0].title)

    win.spec = type(win.spec)(task=seed)
    win._reload_pages()
    win._refresh()
    app.processEvents()
    win._set_depth(["精简"])
    win._autofill()
    app.processEvents()
    check("quick fills frame only", bool(win.spec.role) and not win.spec.success, win.spec.success[:24])

    win.spec = type(win.spec)()
    win._reload_pages()
    win._refresh()
    app.processEvents()
    win._autofill()
    app.processEvents()
    check("autofill guards empty task", win.spec.is_blank(), win.toast.text())

    win.close()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("all smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
