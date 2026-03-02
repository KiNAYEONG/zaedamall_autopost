# tools/sources_pubmed.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import requests
from urllib.parse import quote


def fetch_pubmed_sources(query: str, max_items: int = 4) -> list[str]:
    """
    PubMed(NCBI E-utilities)에서 query로 논문/리뷰를 찾아 '근거자료'로 쓸 수 있게 포맷팅.
    - 무료 / API 키 불필요
    - 실패하면 최소한의 fallback 문구 반환
    """
    query = (query or "").strip()
    if not query:
        return ["PubMed (NCBI): https://pubmed.ncbi.nlm.nih.gov/"]

    try:
        # 1) ESearch: PMID 목록
        esearch = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&retmode=json&retmax={max_items}&sort=relevance&term={quote(query)}"
        )
        r = requests.get(esearch, timeout=10)
        r.raise_for_status()
        pmids = r.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return [
                f"PubMed 검색(키워드: {query}): https://pubmed.ncbi.nlm.nih.gov/?term={quote(query)}"
            ]

        # 2) ESummary: 타이틀/저널/연도
        ids = ",".join(pmids)
        esummary = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&retmode=json&id={ids}"
        )
        r2 = requests.get(esummary, timeout=10)
        r2.raise_for_status()
        data = r2.json().get("result", {})

        out = []
        for pid in pmids:
            item = data.get(pid, {})
            title = (item.get("title") or "").strip().rstrip(".")
            source = (item.get("source") or "").strip()
            pubdate = (item.get("pubdate") or "").strip()
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
            if title:
                line = f"{title} — {source} ({pubdate}) · {url}"
            else:
                line = f"PubMed: {url}"
            out.append(line)

        return out[:max_items]

    except Exception:
        # 네트워크 막힌 환경/일시 장애 등
        return [
            f"PubMed 검색(키워드: {query}): https://pubmed.ncbi.nlm.nih.gov/?term={quote(query)}",
            "NCBI E-utilities (PubMed API): https://www.ncbi.nlm.nih.gov/books/NBK25500/",
        ]
