from app.dental_knowledge_graph import graph_expansion_terms, matched_nodes

def contains(values, term):
    return term.casefold() in " | ".join(values).casefold()

assert any(n.id == "mandible" for n in matched_nodes("alt çene mandibula"))
assert contains(graph_expansion_terms("mandibula sagittal konum kranial kaide"), "SNB")
assert contains(graph_expansion_terms("çalışma boyu"), "apikal konstriksiyon")
assert contains(graph_expansion_terms("periodontal cep"), "sondalama derinliği")
assert contains(graph_expansion_terms("inferior alveolar sinir"), "mandibular kanal")
assert not contains(graph_expansion_terms("üçüncü molar"), "gömülülük")
assert graph_expansion_terms("yarın ders saat kaçta") == []
print("Dental graph checks: OK")

# Short aliases must respect token boundaries as the ontology grows.
assert not any(n.id == "centric_relation" for n in matched_nodes("screen görüntüsü"))
assert not any(n.id == "probing_depth" for n in matched_nodes("rapidly ilerleyen"))
assert any(n.id == "centric_relation" for n in matched_nodes("dental CR ile sentrik ilişki kaydı"))
assert any(n.id == "probing_depth" for n in matched_nodes("periodontal PD 6 mm sondalama"))


def test_explicit_mention_spans_match_canonical_inflected_nodes():
    from app.dental_knowledge_graph import explicit_node_mentions, matched_nodes
    query = "İrreversible pulpitisin tanısı ile mandibular kanalın ilişkisini anlat"
    span_ids = {node.id for _, _, node in explicit_node_mentions(query)}
    exact_ids = {node.id for node in matched_nodes(query)}
    assert {"irreversible_pulpitis", "mandibular_canal"}.issubset(span_ids)
    assert span_ids.issubset(exact_ids)


def test_fuzzy_typo_subject_does_not_receive_fake_explicit_span():
    from app.dental_knowledge_graph import explicit_node_mentions, matched_nodes
    query = "mandbular kanal ilişkisini anlat"
    assert any(node.id == "mandibular_canal" for node in matched_nodes(query))
    assert all(node.id != "mandibular_canal" for _, _, node in explicit_node_mentions(query))



def test_explicit_spans_preserve_safe_turkish_ascii_fallback():
    from app.dental_knowledge_graph import explicit_node_mentions, matched_nodes
    query = "cene iliskisini anlat"
    matched = {node.id for node in matched_nodes(query)}
    spanned = {node.id for _, _, node in explicit_node_mentions(query)}
    assert spanned.issubset(matched)


def test_explicit_spans_still_exclude_edit_distance_typo_rescue():
    from app.dental_knowledge_graph import explicit_node_mentions, matched_nodes
    query = "mandbular kanal anatomisini anlat"
    assert any(node.id == "mandibular_canal" for node in matched_nodes(query))
    assert all(node.id != "mandibular_canal" for _, _, node in explicit_node_mentions(query))


def test_measurement_derivation_is_not_an_impression_subject():
    from app.dental_knowledge_graph import explicit_node_mentions
    for word in ("ölçüm", "ölçümü", "ölçümünü", "ölçümlerin", "ölçümlerini", "olcumunu", "olcumlerin"):
        query = f"{word} açıkla"
        assert all(n.id != "impression" for n in matched_nodes(query)), query
        assert all(n.id != "impression" for _, _, n in explicit_node_mentions(query)), query
    # Genuine impression inflections must continue to resolve in both passes.
    for word in ("ölçü", "ölçünün", "ölçüyü", "ölçülerini", "olcunun"):
        query = f"{word} anlat"
        assert any(n.id == "impression" for n in matched_nodes(query)), query
        assert any(n.id == "impression" for _, _, n in explicit_node_mentions(query)), query
