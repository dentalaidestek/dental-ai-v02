"""Bounded spelling candidates for source search; never rewrite a patient medication."""
import re
import unicodedata


def tokens(text):
    text = unicodedata.normalize('NFKD', text.casefold().replace('ı', 'i'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r'[a-z]+', text)


def supported_search_term(term, quote):
    """A near spelling is only a search hypothesis, not a confirmed ingredient."""
    if not isinstance(term, str) or not re.fullmatch(r'[A-Za-z][A-Za-z -]{2,79}', term):
        return False
    wanted, spoken = tokens(term), tokens(quote)
    if wanted and all(word in spoken for word in wanted):
        return True
    if len(wanted) != 1 or len(wanted[0]) < 7:
        return False
    def phonetic(word):
        word = word.replace('ph', 'f').replace('th', 't').replace('x', 'ks')
        word = re.sub(r'c(?=[eiy])', 's', word)
        return word.replace('c', 'k').replace('y', 'i').replace('w', 'v')
    target = phonetic(wanted[0])
    for word in spoken:
        word = phonetic(word)
        if len(word) < 7 or abs(len(word) - len(target)) > 2:
            continue
        # Levenshtein bound deliberately excludes semantic brand/ingredient substitutions.
        row = list(range(len(target) + 1))
        for i, char in enumerate(word, 1):
            nxt = [i]
            for j, other in enumerate(target, 1):
                nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (char != other)))
            row = nxt
        if row[-1] <= 2 and row[-1] / max(len(word), len(target)) <= .20:
            return True
    return False


def is_spelling_candidate(term, quote):
    return supported_search_term(term, quote) and not all(t in tokens(quote) for t in tokens(term))
