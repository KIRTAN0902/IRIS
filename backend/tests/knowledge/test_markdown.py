from __future__ import annotations

from app.knowledge.markdown import (
    merge_user_section,
    note_path,
    parse_frontmatter,
    render_frontmatter,
    render_index_note,
)


def test_frontmatter_round_trip_and_links():
    metadata = {
        "id": "abc",
        "title": "IRIS Project",
        "tags": ["project", "ai"],
        "active": True,
        "count": 3,
    }
    body = "# IRIS Project\n\nRelated to [[FastAPI]] and [a note](02-Projects/notes.md).\n"
    content = render_frontmatter(metadata) + "\n" + body
    parsed = parse_frontmatter(content)
    assert parsed.frontmatter["id"] == "abc"
    assert parsed.frontmatter["tags"] == ["project", "ai"]
    assert parsed.frontmatter["active"] is True
    assert parsed.frontmatter["count"] == 3
    assert "FastAPI" in parsed.links
    assert "02-Projects/notes.md" in parsed.links


def test_user_notes_section_is_preserved_during_regeneration():
    existing = "# Node\n\n## Knowledge\n\n- old\n\n## Notes\n\nMy own words.\n"
    generated = "# Node\n\n## Knowledge\n\n- new\n\n## Notes\n\n_This section is yours._\n"
    merged = merge_user_section(existing, generated)
    assert "My own words." in merged
    assert "- new" in merged
    assert "_This section is yours._" not in merged


def test_note_paths_follow_category_folders():
    assert note_path("IRIS Project", category="projects").startswith("02-Projects/")
    assert note_path("Morning routine", category="personal").startswith("01-Personal/")
    assert note_path("Unknown", category="nonsense").startswith("00-Index/")


def test_index_note_renders_sections():
    rendered = render_index_note(
        title="Knowledge Index",
        path="00-Index/Knowledge Index.md",
        sections={"Projects": ["IRIS", "Client App"]},
        description="Generated.",
    )
    assert "[[Client App]]" in rendered.content
    assert "## Projects" in rendered.content
    assert rendered.note_type == "index"
