"""Pure-numpy DistilBERT sequence classifier (inference only, no torch needed).

Reimplements HF DistilBertForSequenceClassification + BertTokenizerFast (uncased)
so the SupportIQ model can be evaluated without torch/transformers.
"""
import json
import struct
import unicodedata
import numpy as np
try:
    from scipy.special import erf
except ImportError:  # scipy is optional: Abramowitz-Stegun 7.1.26 (|err| < 1.5e-7)
    def erf(x):
        x = np.asarray(x, dtype=np.float64)
        s = np.sign(x)
        a = np.abs(x)
        t = 1.0 / (1.0 + 0.3275911 * a)
        y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-a * a)
        return s * y

DTYPES = {"F32": np.float32, "F16": np.float16, "I64": np.int64}


def load_safetensors(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
        base = 8 + n
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    out = {}
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        s, e = meta["data_offsets"]
        arr = np.frombuffer(raw[base + s: base + e], dtype=DTYPES[meta["dtype"]]).reshape(meta["shape"])
        out[name] = arr.astype(np.float32)
    return out


# ---------------- tokenizer (BertNormalizer + BertPreTokenizer + WordPiece) -------------
def _is_punct(ch):
    cp = ord(ch)
    if (33 <= cp <= 47) or (58 <= cp <= 64) or (91 <= cp <= 96) or (123 <= cp <= 126):
        return True
    return unicodedata.category(ch).startswith("P")


def _is_cjk(cp):
    return ((0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0x20000 <= cp <= 0x2A6DF)
            or (0x2A700 <= cp <= 0x2B73F) or (0x2B740 <= cp <= 0x2B81F) or (0x2B820 <= cp <= 0x2CEAF)
            or (0xF900 <= cp <= 0xFAFF) or (0x2F800 <= cp <= 0x2FA1F))


class Tokenizer:
    def __init__(self, path, max_length=64):
        t = json.load(open(path, encoding="utf-8"))
        self.vocab = t["model"]["vocab"]
        self.unk = self.vocab["[UNK]"]
        self.cls = self.vocab["[CLS]"]
        self.sep = self.vocab["[SEP]"]
        self.max_length = max_length

    def normalize(self, text):
        out = []
        for ch in text:
            cp = ord(ch)
            if cp == 0 or cp == 0xFFFD or (unicodedata.category(ch).startswith("C") and ch not in "\t\n\r"):
                continue
            if ch in "\t\n\r" or unicodedata.category(ch) == "Zs":
                out.append(" ")
            elif _is_cjk(cp):
                out.append(f" {ch} ")
            else:
                out.append(ch)
        text = "".join(out).lower()
        text = unicodedata.normalize("NFD", text)
        return "".join(c for c in text if unicodedata.category(c) != "Mn")

    def pre_tokenize(self, text):
        words, cur = [], []
        for ch in text:
            if ch.isspace():
                if cur:
                    words.append("".join(cur)); cur = []
            elif _is_punct(ch):
                if cur:
                    words.append("".join(cur)); cur = []
                words.append(ch)
            else:
                cur.append(ch)
        if cur:
            words.append("".join(cur))
        return words

    def wordpiece(self, word):
        if len(word) > 100:
            return [self.unk]
        ids, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while start < end:
                sub = word[start:end]
                if start > 0:
                    sub = "##" + sub
                if sub in self.vocab:
                    found = self.vocab[sub]; break
                end -= 1
            if found is None:
                return [self.unk]
            ids.append(found); start = end
        return ids

    def encode(self, text):
        ids = []
        for w in self.pre_tokenize(self.normalize(text)):
            ids.extend(self.wordpiece(w))
        truncated = len(ids) > self.max_length - 2
        ids = ids[: self.max_length - 2]
        return [self.cls] + ids + [self.sep], truncated


# ---------------- model -------------
def layer_norm(x, w, b, eps=1e-12):
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * w + b


def gelu(x):
    return 0.5 * x * (1.0 + erf(x / np.sqrt(2.0)))


class DistilBertClassifier:
    def __init__(self, model_dir):
        self.cfg = json.load(open(f"{model_dir}/config.json"))
        self.W = load_safetensors(f"{model_dir}/model.safetensors")
        self.tok = Tokenizer(f"{model_dir}/tokenizer.json")
        self.id2label = {int(k): v for k, v in self.cfg["id2label"].items()}
        self.n_heads = self.cfg["n_heads"]

    def lin(self, x, name):
        return x @ self.W[name + ".weight"].T + self.W[name + ".bias"]

    def logits(self, ids):
        W, p = self.W, "distilbert."
        n = len(ids)
        x = W[p + "embeddings.word_embeddings.weight"][ids] + W[p + "embeddings.position_embeddings.weight"][:n]
        x = layer_norm(x, W[p + "embeddings.LayerNorm.weight"], W[p + "embeddings.LayerNorm.bias"])
        H = self.n_heads
        d = x.shape[-1] // H
        for i in range(self.cfg["n_layers"]):
            L = f"{p}transformer.layer.{i}."
            q = self.lin(x, L + "attention.q_lin").reshape(n, H, d).transpose(1, 0, 2) / np.sqrt(d)
            k = self.lin(x, L + "attention.k_lin").reshape(n, H, d).transpose(1, 0, 2)
            v = self.lin(x, L + "attention.v_lin").reshape(n, H, d).transpose(1, 0, 2)
            s = q @ k.transpose(0, 2, 1)
            s = np.exp(s - s.max(-1, keepdims=True)); s /= s.sum(-1, keepdims=True)
            a = (s @ v).transpose(1, 0, 2).reshape(n, H * d)
            x = layer_norm(self.lin(a, L + "attention.out_lin") + x, W[L + "sa_layer_norm.weight"], W[L + "sa_layer_norm.bias"])
            f = self.lin(gelu(self.lin(x, L + "ffn.lin1")), L + "ffn.lin2")
            x = layer_norm(f + x, W[L + "output_layer_norm.weight"], W[L + "output_layer_norm.bias"])
        h = np.maximum(self.lin(x[0], "pre_classifier"), 0.0)
        return self.lin(h, "classifier")

    def predict(self, text, k=3):
        ids, truncated = self.tok.encode(text)
        z = self.logits(ids).astype(np.float64)
        pr = np.exp(z - z.max()); pr /= pr.sum()
        order = np.argsort(-pr)
        return {
            "intent": self.id2label[int(order[0])],
            "confidence": float(pr[order[0]]),
            "margin": float(pr[order[0]] - pr[order[1]]),
            "top_k": [(self.id2label[int(j)], float(pr[j])) for j in order[:k]],
            "entropy": float(-(pr * np.log(pr + 1e-12)).sum()),
            "n_tokens": len(ids),
            "truncated": truncated,
            "logits": z,
        }
