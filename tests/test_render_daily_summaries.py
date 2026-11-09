from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).parents[1] / "daily" / "_engine" / "render_daily.py"
SPEC = importlib.util.spec_from_file_location("render_daily", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
render_daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_daily)


def test_link_after_title_keeps_following_summary():
    item = render_daily._parse_item(
        "**金刚石散热**:[Diamond Foundry](https://example.com/wafer),导热远超铜,瞄准 AI 芯片散热。"
    )
    assert item["title"] == "金刚石散热"
    assert item["url"] == "https://example.com/wafer"
    assert item["summary"] == "Diamond Foundry,导热远超铜,瞄准 AI 芯片散热。"


def test_link_inside_summary_is_retained_as_text():
    item = render_daily._parse_item(
        "**许可风险**:[报道](https://example.com/report)揭示出口审查漏洞。"
    )
    assert item["title"] == "许可风险"
    assert item["summary"] == "报道揭示出口审查漏洞。"


def test_source_only_link_after_summary_is_not_shown_as_summary():
    item = render_daily._parse_item(
        "**PyTorch**。训练容错下沉到框架层（[The Register](https://example.com/pytorch)）。"
    )
    assert item["summary"] == "训练容错下沉到框架层。"


def test_legacy_link_at_end_format_preserves_summary():
    item = render_daily._parse_item(
        "**PyTorch 2.15 正面处理坏 GPU**。万卡集群的节点容错更重要（[The Register](https://example.com/pytorch)）。"
    )
    assert item["title"] == "PyTorch 2.15 正面处理坏 GPU"
    assert item["summary"].startswith("万卡集群的节点容错更重要")
    assert "The Register" not in item["summary"]
