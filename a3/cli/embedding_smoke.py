import importlib.metadata as metadata
import math
import platform
from a3.indexing.embeddings import BgeM3EmbeddingProvider
def main():
    import torch
    print("Python",platform.python_version()); print("FlagEmbedding",metadata.version("FlagEmbedding")); print("torch",torch.__version__)
    print("device","cuda" if torch.cuda.is_available() else "cpu"); provider=BgeM3EmbeddingProvider(use_fp16=torch.cuda.is_available())
    vectors=provider.encode_queries(["中文医学工程测试", "English medical engineering fixture"])
    assert vectors and len(vectors[0])==len(vectors[1]) and all(math.isfinite(x) for v in vectors for x in v)
    norms=[math.sqrt(sum(value*value for value in vector)) for vector in vectors]
    assert all(abs(norm-1.0)<1e-3 for norm in norms)
    print("model",provider.model_id,"source",provider.source_kind,"revision",provider.revision,
        "precision","fp16" if torch.cuda.is_available() else "fp32","dimension",len(vectors[0]),"norms",norms)
if __name__ == "__main__": main()
