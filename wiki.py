"""Wiki browser backend: tree building from unified wiki_pages table."""

from __future__ import annotations

from database import list_wiki_pages


def build_wiki_tree(include_d2: bool = False, is_doc: bool = False) -> list[dict]:
    """Build a nested tree structure.

    When include_d2 is True, knowledge_type='d2' pages are included under
    a virtual "研发知识库 (D2)" root node.
    When is_doc is True, draft/pending_review D1 pages are also shown.
    """
    pages = list_wiki_pages()
    visible = []
    d2_pages = []
    for p in pages:
        kt = p.get("knowledge_type", "d1")
        st = p.get("status", "draft")
        if kt == "d2":
            if include_d2:
                d2_pages.append(p)
            continue
        # d1: show approved to all; show draft/pending_review to doc
        if st == "approved" or (is_doc and st in ("draft", "pending_review")):
            visible.append(p)

    # Build adjacency map for D1
    children_map: dict[int, list[dict]] = {}
    for p in visible:
        pid = p.get("parent_id") or 0
        children_map.setdefault(pid, []).append(p)

    for children in children_map.values():
        children.sort(key=lambda x: x.get("created_at", ""))

    def build_node(page: dict) -> dict:
        node = {
            "id": page["id"],
            "slug": page["slug"],
            "title": page["title"],
            "parent_id": page.get("parent_id"),
            "owner": page.get("owner", ""),
            "updated_at": page.get("updated_at", ""),
            "source": page.get("knowledge_type", "d1"),
            "status": page.get("status", ""),
        }
        children = children_map.get(page["id"], [])
        if children:
            node["children"] = [build_node(c) for c in children]
        return node

    roots_list = [build_node(r) for r in children_map.get(0, [])]

    # Add D2 section
    if include_d2 and d2_pages:
        d2_children = []
        for p in d2_pages:
            entry_type = p.get("entry_type", "")
            label = {
                "solution": "[方案] ",
                "release_note": "[发布] ",
            }.get(entry_type, "")
            d2_children.append({
                "id": p["id"],
                "slug": p["slug"],
                "title": label + p["title"],
                "parent_id": None,
                "owner": p.get("owner", "rd"),
                "updated_at": p.get("created_at", ""),
                "source": "d2",
                "version": p.get("version", ""),
                "entry_type": entry_type,
                "status": p.get("status", "draft"),
                "children": [],
            })
        roots_list.append({
            "id": 0,
            "slug": "",
            "title": "研发知识库 (D2)",
            "parent_id": None,
            "owner": "",
            "updated_at": "",
            "source": "d2-folder",
            "children": d2_children,
        })
    return roots_list
