# Dental source coverage

User intent: handle the full range of dental encounters without requiring the user to enumerate each complication. Preserve Finish-only processing, review_provider, closed topic IDs, physician approval, privacy, bounded work and recovery. User explicitly requests implementation and opts out of another question/approval round.

Approach: extend the existing closed taxonomy with hierarchical branch fallbacks and common procedure/complication scopes; give the existing extraction call semantic descriptions. Keep legacy IDs. Fixed server-owned scientific queries and verified professional-source mappings cover each branch. No model-authored URLs/searches and no extra model call. PubMed alone and keyword-only routing cannot meet the requested breadth; unrestricted web search violates the existing closed-query design.

Do not claim a finite taxonomy/source list proves every clinical situation. Select the nearest branch for unfamiliar manifestations, retain specificity as uncertainty, and expose per-topic source coverage rather than presenting unrelated drug/general sources as an answer. No attribution of professional error from an incomplete conversation.

Separate topic extraction capacity (24) from remote retrieval wait budgets. Preserve all accepted topics in context; any capacity/coverage gap remains explicit. More than 24 topics must fail with draft-preserving error rather than truncate. Existing 24KB context and source/prompt budgets remain.

Professional source pages are bounded excerpts, not complete guideline ingestion. No PDF parser, provider switch, full-transcript persistence, main merge or deployment in this change. Keep existing document fallbacks for older clients. New selection metadata must guide the model semantically, not turn patient examples into free search queries.
