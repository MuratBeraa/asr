"""RAG servisi — ChromaDB + sentence-transformers ile kampanya retrieval."""
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = BASE_DIR / "chroma_db"
CAMPAIGNS_FILE = DATA_DIR / "campaigns.json"

EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


class CustomEmbedding(embedding_functions.EmbeddingFunction):
    def __init__(self):
        self.model = SentenceTransformer(EMBED_MODEL_NAME)

    def __call__(self, input):
        return self.model.encode(input, convert_to_numpy=True).tolist()


class RAGService:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.embed_fn = CustomEmbedding()

        self.collection = self.client.get_or_create_collection(
            name="eminevim_campaigns",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        # İlk çalıştırmada veri yükle
        if self.collection.count() == 0:
            print("[rag] ChromaDB boş, kampanyalar yükleniyor...")
            self._index_campaigns()
            print(f"[rag] {self.collection.count()} kampanya yüklendi.")

    def _index_campaigns(self):
        """campaigns.json'u okuyup ChromaDB'ye indexle."""
        with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        ids = []
        documents = []
        metadatas = []

        for c in data["campaigns"]:
            # Contextual retrieval: bağlam + kampanya metni
            doc_text = c["contextual"] + " " + c["aciklama"]
            ids.append(c["id"])
            documents.append(doc_text)
            metadatas.append({
                "ad": c["ad"],
                "pesinat_min": c["pesinat_min"],
                "pesinat_max": c["pesinat_max"],
                "taksit_min": c["taksit_min"],
                "taksit_max": c["taksit_max"],
                "vade_ay": c["vade_ay"],
                "sistem": c["sistem"],
                "hedef_kitle": c["hedef_kitle"],
                "ozellikler": ", ".join(c["ozellikler"]),
                "aciklama": c["aciklama"],
            })

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(self, query: str, top_k: int = 5):
        """Konuşma metnine göre en ilgili kampanyaları bul."""
        if not query.strip():
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
        )

        campaigns = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            campaigns.append({
                "id": results["ids"][0][i],
                "ad": meta["ad"],
                "pesinat_min": meta["pesinat_min"],
                "pesinat_max": meta["pesinat_max"],
                "taksit_min": meta["taksit_min"],
                "taksit_max": meta["taksit_max"],
                "vade_ay": meta["vade_ay"],
                "sistem": meta["sistem"],
                "hedef_kitle": meta["hedef_kitle"],
                "ozellikler": meta["ozellikler"],
                "aciklama": meta["aciklama"],
                "similarity": 1 - results["distances"][0][i] if "distances" in results else None,
            })

        return campaigns

    def format_for_llm(self, campaigns: list) -> str:
        """Kampanyaları LLM prompt'u için metin haline getir."""
        if not campaigns:
            return "(Bu konuşmayla ilgili kampanya bulunamadı)"

        lines = []
        for c in campaigns:
            lines.append(
                f"--- {c['id']}: {c['ad']} ---\n"
                f"Peşinat: {c['pesinat_min']:,}-{c['pesinat_max']:,} TL\n"
                f"Taksit: {c['taksit_min']:,}-{c['taksit_max']:,} TL/ay\n"
                f"Vade: {c['vade_ay']} ay\n"
                f"Sistem: {c['sistem']}\n"
                f"Hedef: {c['hedef_kitle']}\n"
                f"Özellikler: {c['ozellikler']}\n"
                f"Açıklama: {c['aciklama']}\n"
            )
        return "\n".join(lines)


# Singleton
_rag_instance = None


def get_rag():
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGService()
    return _rag_instance