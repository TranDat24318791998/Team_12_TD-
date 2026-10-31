"""Shared content vocabulary and numeric-claim check."""

import re
import unicodedata


def content_matches_facts(text, sources):
    neutral={'và','với','có','của','cho','là','được','từ','như','để','trong',
             'theo','bằng','sản','phẩm','khi','một','các','dùng','sử','dụng'}
    def clauses(value):
        value=unicodedata.normalize('NFC',value).casefold()
        return [[word for word in re.findall(r'\w+',clause) if word not in neutral]
                for clause in re.split(r'[,;:!?]|(?<!\d)\.(?!\d)',value)]
    source_clauses=[tokens for source in sources for tokens in clauses(source)]
    allowed={word for tokens in source_clauses for word in tokens}|neutral
    if not set(re.findall(r'\w+',unicodedata.normalize('NFC',text).casefold()))<=allowed:
        return False
    pairs={(a,b) for tokens in source_clauses for a,b in zip(tokens,tokens[1:])}
    for tokens in clauses(text):
        for index,token in enumerate(tokens):
            if not re.search(r'\d',token): continue
            adjacent=set()
            if index: adjacent.add((tokens[index-1],token))
            if index+1<len(tokens): adjacent.add((token,tokens[index+1]))
            if not adjacent.intersection(pairs): return False
    return True
