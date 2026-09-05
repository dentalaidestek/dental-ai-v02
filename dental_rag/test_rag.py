from rag import get_relevant_context

print("DENTAL RAG TEST")
print("================")

context = get_relevant_context(
    "dental caries treatment tooth pain",
    top_k=4
)

if context:
    print("RAG çalışıyor.")
    print()
    print(context)
else:
    print("RAG motoru çalışıyor fakat henüz klinik kaynak eklenmemiş.")
