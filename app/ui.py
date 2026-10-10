"""Shared UI helpers. Keep pages thin: they call these and swap in real data later."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DOCS = REPO_ROOT / "docs"

CORE_RULE = (
    "**Core rule:** ML models predict · the carbon engine / calculators compute impact · "
    "the LLM only explains structured outputs. A propensity never establishes eligibility."
)


def header(title: str, subtitle: str = "", *, todo: str = "") -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)
    st.warning(
        "PLACEHOLDER PAGE – all numbers below are mock values, not model output."
        + (f"\n\n**TODO:** {todo}" if todo else ""),
        icon="🚧",
    )


def estimate_label(text: str = "Estimate, not a guarantee · method documented in docs/") -> None:
    st.caption(f"ⓘ {text}")


def core_rule() -> None:
    st.info(CORE_RULE, icon="⚖️")


def read_doc(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def mermaid(code: str, height: int = 600) -> None:
    """Render Mermaid in the browser (CDN, pinned version)."""
    safe = code.replace("</", "<\\/")
    html = (
        f"""
        <div class="mermaid">{safe}</div>
        <script type="module">
          import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";
          mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
        </script>
        """
    )
    if hasattr(st, "iframe"):  # newer Streamlit; components.html is deprecated
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=True)
