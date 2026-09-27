from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
STYLE = (ROOT / "app/static/style.css").read_text(encoding="utf-8")


def _mobile_nav_markup():
    start = BASE.index('<nav class="mobile-bottom-nav"')
    end = BASE.index("</nav>", start) + len("</nav>")
    return BASE[start:end]


def test_mobile_bottom_nav_has_five_expected_destinations():
    nav = _mobile_nav_markup()
    hrefs = re.findall(r'<a href="([^"]+)" class="mobile-nav-item', nav)
    assert hrefs == ["/", "/patients", "/analysis/new", "/messages", "/account"]


def test_mobile_bottom_nav_is_outside_main_and_normal_routes_render_it():
    main_end = BASE.index("</main>")
    nav_start = BASE.index('<nav class="mobile-bottom-nav"')
    assert nav_start > main_end
    assert '{% if user and not request.url.path.startswith("/expert-support/cases/") %}' in BASE[:nav_start]


def test_mobile_bottom_nav_mobile_contract_is_fixed_five_columns():
    match = re.search(
        r"\.mobile-bottom-nav\s*\{(?P<body>[^}]*)\}",
        STYLE,
        flags=re.S,
    )
    assert match, "mobile bottom nav base rule is missing"
    body = re.sub(r"\s+", " ", match.group("body"))
    assert "display: grid" in body
    assert "grid-template-columns: repeat(5, 1fr)" in body
    assert "position: fixed" in body
    assert "left: 0" in body and "right: 0" in body and "bottom: 0" in body
    assert "z-index: 1200" in body


def test_only_case_room_mobile_rule_force_hides_bottom_nav():
    force_hide = re.findall(
        r"([^{}]+\.mobile-bottom-nav[^{}]*)\{([^{}]*display\s*:\s*none\s*!important[^{}]*)\}",
        STYLE,
        flags=re.S,
    )
    assert force_hide, "expected case-room hide rule is missing"
    selectors = [" ".join(selector.split()) for selector, _ in force_hide]
    assert selectors == ["body:has(main .expert-room) .mobile-bottom-nav"]


def test_partial_navigation_only_toggles_whole_nav_visibility():
    # It may hide/show the whole bar while entering/leaving a case room, but must
    # never mutate layout or selectively remove navigation items.
    assert 'bottomNav.hidden=true' in BASE or 'bottomNav.hidden = true' in BASE
    assert 'bottomNav.hidden=snapshot.bottomNavHidden' in BASE or 'bottomNav.hidden = snapshot.bottomNavHidden' in BASE
    forbidden = (
        "bottomNav.style.position",
        "bottomNav.style.display",
        "bottomNav.style.gridTemplateColumns",
        "mobile-nav-item:nth-child",
    )
    for token in forbidden:
        assert token not in BASE
