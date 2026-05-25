from __future__ import annotations

from fastembed.rerank.cross_encoder import TextCrossEncoder

from mcp_server.services.protocols import RerankerInterface, SearchHit


class FastEmbedCrossEncoderReranker(RerankerInterface):
    def __init__(self, model_name: str) -> None:
        self._model = TextCrossEncoder(model_name=model_name)

    def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        if not hits:
            return hits
        passages = [h["passage_snippet"] for h in hits]
        scores = list(self._model.rerank(query, passages))
        ranked = sorted(zip(hits, scores), key=lambda pair: pair[1], reverse=True)[:top_k]
        result = []
        for hit, score in ranked:
            hit["similarity_score"] = float(score)
            result.append(hit)
        return result
