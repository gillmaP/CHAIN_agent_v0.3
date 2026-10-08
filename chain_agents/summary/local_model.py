"""Offline model loading shared by the Summary extractor; no evaluation or downloads."""
import os
import time

MODELS = {
    "qwen35_9b": {"repo_id": "Qwen/Qwen3.5-9B", "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "directory": "Qwen3.5-9B", "license": "Apache-2.0", "parameter_label": "9B"},
    "qwen25_14b_instruct": {"repo_id": "Qwen/Qwen2.5-14B-Instruct", "revision": "cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8", "directory": "Qwen2.5-14B-Instruct", "license": "Apache-2.0", "parameter_label": "14B", "loader": "causal"},
    "gemma4_12b_it": {"repo_id": "google/gemma-4-12B-it", "revision": "707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7", "directory": "gemma-4-12B-it", "license": "Apache-2.0", "parameter_label": "12B"},
    "medgemma15_4b_it": {"repo_id": "google/medgemma-1.5-4b-it", "revision": "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b", "directory": "medgemma-1.5-4b-it", "license": "HAI-DEF Terms of Use", "parameter_label": "4B"},
}

def model_config(model_key):
    try:
        return MODELS[model_key]
    except KeyError as exc:
        raise ValueError(f"Unknown model {model_key!r}; choose one of {sorted(MODELS)}") from exc


class LocalModel:
    def __init__(self, model_key, model_dir, gpu_index="0", max_new_tokens=8192):
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; local inference requires a GPU.")
        self.model_key = model_key
        self.spec = model_config(model_key)
        self.torch, self.model_dir, self.max_new_tokens = torch, model_dir, max_new_tokens
        if self.spec.get("loader") == "causal":
            from transformers import AutoModelForCausalLM, AutoTokenizer
            processor_class, model_class = AutoTokenizer, AutoModelForCausalLM
        else:
            from transformers import AutoModelForMultimodalLM, AutoProcessor
            processor_class, model_class = AutoProcessor, AutoModelForMultimodalLM
        started = time.perf_counter()
        self.processor = processor_class.from_pretrained(str(model_dir), local_files_only=True)
        self.model = model_class.from_pretrained(
            str(model_dir), local_files_only=True, device_map="auto",
            dtype="auto", low_cpu_mem_usage=True,
        )
        self.model.eval()
        self.load_seconds = time.perf_counter() - started

