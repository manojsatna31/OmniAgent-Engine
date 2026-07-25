import html
import os
import re
from pathlib import Path

import streamlit as st

from agent import agent_executor
from logger import setup_logger


# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
logger = setup_logger("PublishAI")

st.set_page_config(
    page_title="PublishAI Content Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ------------------------------------------------------------
# CSS loader
# ------------------------------------------------------------
def load_css(file_path: Path) -> None:
    try:
        if file_path.exists():
            css = file_path.read_text(encoding="utf-8")
            st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except Exception as exc:
        logger.warning("Unable to load CSS: %s", exc)


load_css(Path(__file__).parent / "assets" / "style.css")


# ------------------------------------------------------------
# Draft helpers
# ------------------------------------------------------------
def get_articles():
    drafts_dir = Path("drafts")
    if not drafts_dir.exists():
        return []

    articles = []
    for filepath in drafts_dir.rglob("*.md"):
        try:
            first_line = filepath.read_text(encoding="utf-8").splitlines()[0].strip()
            if first_line.startswith("# "):
                title = first_line[2:]
            else:
                title = filepath.stem.replace("-", " ").replace("_", " ").title()
        except Exception:
            title = filepath.stem.replace("-", " ").replace("_", " ").title()

        articles.append((title, str(filepath)))

    articles.sort(key=lambda item: os.path.getmtime(item[1]), reverse=True)
    return articles


def read_article(filepath: str) -> str:
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Unable to read article %s: %s", filepath, exc)
        return "Unable to load this article."


def article_meta(filepath: str):
    modified = Path(filepath).stat().st_mtime
    from datetime import datetime

    dt = datetime.fromtimestamp(modified)
    return dt.strftime("%b %d, %Y"), dt.strftime("%I:%M %p")


# ------------------------------------------------------------
# Reusable UI helpers
# ------------------------------------------------------------
def render_topbar() -> None:
    left, right = st.columns([0.8, 0.2], vertical_alignment="center")

    with left:
        st.markdown(
            """
            <div class="topbar-brand">
                <div class="brand-mark">✦</div>
                <div>
                    <div class="brand-name">PublishAI</div>
                    <div class="brand-subtitle">Content Agent</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            """
            <div class="topbar-status">
                <span class="status-dot"></span>
                AI workspace ready
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-shell">
            <div class="hero-badge">AI-powered technical publishing</div>
            <h1 class="hero-title">Research once. Publish everywhere.</h1>
            <p class="hero-copy">
                Turn a technical idea into a polished LinkedIn post, Dev.to article, README,
                or long-form engineering draft with a cleaner AI writing workflow.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_prompt_chips() -> None:
    st.markdown(
        """
        <div class="section-heading-row">
            <div>
                <div class="section-kicker">Quick start</div>
                <h2 class="section-title">Choose a writing workflow</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    active_type = st.session_state.get("content_type", DEFAULT_CONTENT_TYPE)
    chip_cols = st.columns(4)

    for col, content_type in zip(chip_cols, CONTENT_TYPES):
        with col:
            is_active = content_type == active_type
            label = f"✓ {content_type}" if is_active else content_type
            if st.button(label, key=f"chip_{content_type}", use_container_width=True):
                st.session_state["content_type"] = content_type
                st.rerun()

    st.markdown(
        f"""
        <div class="mode-indicator">Active mode: <span class="mode-indicator-value">{active_type}</span></div>
        """,
        unsafe_allow_html=True,
    )


def render_article_library() -> None:
    articles = get_articles()
    last_saved = st.session_state.get("last_saved_file")

    st.markdown(
        """
        <div class="section-heading-row">
            <div>
                <div class="section-kicker">Library</div>
                <h2 class="section-title">Recent generated articles</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not articles:
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-icon">📚</div>
                <div class="empty-title">No generated articles yet</div>
                <div class="empty-copy">Your saved Markdown drafts will appear here automatically.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for index, (title, filepath) in enumerate(articles[:8]):
        date_text, time_text = article_meta(filepath)
        is_new = filepath == last_saved

        safe_title = html.escape(title)
        new_badge_html = '<span class="new-badge">New</span>' if is_new else ''

        card_html = (
            '<div class="article-card">'
            '<div class="article-card-main">'
            '<div class="article-card-topline">'
            f'<span class="article-type-badge">Markdown</span>{new_badge_html}'
            '</div>'
            f'<div class="article-card-title">{safe_title}</div>'
            f'<div class="article-card-meta">Updated {date_text} at {time_text}</div>'
            '</div>'
            '</div>'
        )

        st.markdown(
            card_html,
            unsafe_allow_html=True,
        )

        with st.expander("Open article", expanded=is_new):
            st.markdown(read_article(filepath))
            st.caption(filepath)


def render_chat_history() -> None:
    st.markdown(
        """
        <div class="section-heading-row chat-heading">
            <div>
                <div class="section-kicker">Workspace</div>
                <h2 class="section-title">PublishAI assistant</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.messages:
        st.markdown(
            """
            <div class="assistant-welcome">
                <div class="assistant-avatar">✦</div>
                <div>
                    <div class="assistant-name">PublishAI</div>
                    <div class="assistant-copy">
                        Tell me the topic, target platform, tone, and depth you need.
                        I'll research and turn it into a publishable draft.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for msg in st.session_state.messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")

        if role == "user":
            st.markdown(
                """
                <div class="user-message-wrap">
                    <div class="user-message-bubble">User</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"<div class='user-message-content'>{content}</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                """
                <div class="assistant-message-head">
                    <div class="assistant-avatar small">✦</div>
                    <div class="assistant-name">PublishAI</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(content)


def render_chat_input() -> None:
    content_type = st.session_state.get("content_type", DEFAULT_CONTENT_TYPE)
    user_input = st.chat_input(f"Ask PublishAI to write a {content_type} about...")

    if not user_input:
        return

    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner(f"Researching and writing your {content_type}... This may take a minute."):
        try:
            result = agent_executor.invoke({"input": user_input, "content_type": content_type})
            output = result["output"]

            match = re.search(r"📁\s*(Draft saved successfully:\s*(\S+))", output)
            if match:
                saved_path = match.group(2).replace("\\", "/")
                if saved_path.startswith("drafts/"):
                    st.session_state["last_saved_file"] = saved_path
                    logger.info("New article saved: %s", saved_path)
                else:
                    st.session_state["last_saved_file"] = None
            else:
                st.session_state["last_saved_file"] = None

            st.session_state.messages.append({"role": "assistant", "content": output})
            st.rerun()

        except Exception as exc:
            error_msg = f"❌ Error: {exc}"
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            st.rerun()


def render_debug_panel() -> None:
    if hasattr(agent_executor, "last_messages"):
        with st.expander("Debug: Agent reasoning steps"):
            for msg in agent_executor.last_messages:
                if hasattr(msg, "type"):
                    st.markdown(f"**{msg.type}**")
                if hasattr(msg, "content"):
                    text = msg.content
                    if len(text) > 600:
                        text = text[:600] + "..."
                    st.text(text)


def render_footer() -> None:
    st.markdown(
        """
        <div class="app-footer">
            PublishAI · AI Research & Content Studio
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------
CONTENT_TYPES = ["LinkedIn Post", "Dev.to Article", "README Draft", "Research Topic"]
DEFAULT_CONTENT_TYPE = "LinkedIn Post"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "content_type" not in st.session_state:
    st.session_state.content_type = DEFAULT_CONTENT_TYPE


# ------------------------------------------------------------
# App layout
# ------------------------------------------------------------
render_topbar()
render_hero()
render_prompt_chips()

st.divider()

render_article_library()

st.divider()

render_chat_history()
render_chat_input()
render_debug_panel()
render_footer()