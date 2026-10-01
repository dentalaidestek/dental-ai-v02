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
