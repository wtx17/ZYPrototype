"""Wiki browser backend: tree building from unified wiki_pages table."""

from __future__ import annotations

from database import list_wiki_pages

ENTRY_TYPE_CATEGORIES = [
    ("general", "通用文档"),
    ("solution", "技术方案"),
    ("release_note", "发布说明"),
]


def build_wiki_tree(include_d2: bool = False, is_doc: bool = False) -> list[dict]:
    """Build a nested tree grouped by entry_type category.

    Top level: virtual category nodes (通用文档, 技术方案, 发布说明).
    Within each category: pages grouped by parent_id preserving hierarchy.
    When include_d2 is True, a "研发知识库 (D2)" section is appended.
    When is_doc is True, draft/pending_review D1 pages are also shown.
    """
    pages = list_wiki_pages()
    d1_pages = []
    d2_pages = []
    for p in pages:
        kt = p.get("knowledge_type", "d1")
        st = p.get("status", "draft")
        if kt == "d2":
            if include_d2:
                d2_pages.append(p)
            continue
        if st == "approved" or (is_doc and st in ("draft", "pending_review")):
            d1_pages.append(p)

    def build_page_node(p: dict) -> dict:
        return {
            "id": p["id"],
            "slug": p["slug"],
            "title": p["title"],
            "parent_id": p.get("parent_id"),
            "owner": p.get("owner", ""),
            "updated_at": p.get("updated_at", ""),
            "source": p.get("knowledge_type", "d1"),
            "status": p.get("status", ""),
            "entry_type": p.get("entry_type", ""),
        }

    def build_hierarchy(pages_in_category: list[dict]) -> list[dict]:
        """Build parent-child tree from flat page list."""
        node_map: dict[int, dict] = {}
        roots = []
        for p in pages_in_category:
            node = build_page_node(p)
            node_map[p["id"]] = node
        for p in pages_in_category:
            node = node_map[p["id"]]
            pid = p.get("parent_id")
            if pid and pid in node_map:
                parent = node_map[pid]
                parent.setdefault("children", []).append(node)
            else:
                roots.append(node)
        # Sort each level by created_at
        def sort_children(n: dict):
            if "children" in n:
                n["children"].sort(key=lambda x: x.get("id", 0))
                for c in n["children"]:
                    sort_children(c)
        for r in roots:
            sort_children(r)
        roots.sort(key=lambda x: x.get("id", 0))
        return roots

    # D1 section: entry_type categories nested under 客服知识库 (D1)
    d1_section_children = []
    for entry_type, category_title in ENTRY_TYPE_CATEGORIES:
        cat_pages = [p for p in d1_pages if p.get("entry_type", "") == entry_type]
        if not cat_pages:
            continue
        cat_children = build_hierarchy(cat_pages)
        d1_section_children.append({
            "id": 0,
            "slug": "",
            "title": category_title,
            "parent_id": None,
            "owner": "",
            "updated_at": "",
            "source": "d1-folder",
            "status": "",
            "children": cat_children,
        })

    roots_list = []
    if d1_section_children:
        roots_list.append({
            "id": 0,
            "slug": "",
            "title": "客服知识库 (D1)",
            "parent_id": None,
            "owner": "",
            "updated_at": "",
            "source": "d1-root",
            "status": "",
            "children": d1_section_children,
        })

    # D2 section
    if include_d2 and d2_pages:
        d2_children = []
        for p in d2_pages:
            et = p.get("entry_type", "")
            label = {"solution": "[方案] ", "release_note": "[发布] "}.get(et, "")
            d2_children.append({
                "id": p["id"],
                "slug": p["slug"],
                "title": label + p["title"],
                "parent_id": None,
                "owner": p.get("owner", "rd"),
                "updated_at": p.get("created_at", ""),
                "source": "d2",
                "entry_type": et,
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
            "source": "d2-root",
            "status": "",
            "children": d2_children,
        })
    return roots_list
