"""Ticket 10-ii probe: build the pinned model, load the checkpoint, freeze, size it.

Runs inside the pinned Python 3.8 venv that ``kaggle/e2e/main.py`` builds
(torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0, mmdet3d from da93b27).

Scope is deliberately narrow: no nuScenes dataloader, no forward, no backward,
no s/step.  Every number printed here is either read from the real model
(param counts) or from the real file (checkpoint sha256).

Each step prints one ``PROBE_STEP <name> <payload>`` line; the run ends with
``PROBE_OK <json>`` or ``PROBE_FAILED <reasons>``.
"""

import copy
import hashlib
import json
import os
import pathlib
import shutil
import sys
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CKPT_URL = (
    "https://huggingface.co/SCU-VIP-Lab/Pretrained_BEVFusion/resolve/main/"
    "bevfusion-det.pth"
)
CKPT_SHA256 = "ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122"
CKPT_PATH = pathlib.Path("/kaggle/working/bevfusion-det.pth")
OUT_JSON = pathlib.Path("/kaggle/working/probe.json")

# Leaf config named by the ticket.  It is a vendor fragment: it does not
# declare ``model.fuser``, so the chain resolved from it has ``fuser: null``.
MODEL_CONFIG = (
    "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/camera+lidar/"
    "swint_v0p075/default.yaml"
)
# The leaf the vendor README pairs with bevfusion-det.pth; it only adds the
# ConvFuser block on top of the same chain.
FALLBACK_CONFIG = (
    "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/camera+lidar/"
    "swint_v0p075/convfuser.yaml"
)

FP32_BYTES = 4
GIB = float(1 << 30)


def log_step(name, payload, summary=None):
    """Emit ``PROBE_STEP <name> [<summary>] <json>``.

    ``summary`` is the compact, grep-friendly form the acceptance criteria name
    (``missing=0``, ``n_trainable_params=...``); the JSON that follows is the
    full evidence.
    """
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, default=str)
    parts = ["PROBE_STEP", name]
    if summary:
        parts.append(summary)
    parts.append(payload)
    print(" ".join(parts), flush=True)


def fail(name, detail):
    print("PROBE_FAILED %s" % name, flush=True)
    print(detail, flush=True)
    sys.exit(1)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------- step 1: file
def ensure_checkpoint():
    if not CKPT_PATH.is_file():
        CKPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            CKPT_URL, headers={"User-Agent": "bevfusion-spray-probe"}
        )
        partial = CKPT_PATH.with_suffix(CKPT_PATH.suffix + ".part")
        with urllib.request.urlopen(request, timeout=300) as response:
            with open(partial, "wb") as handle:
                shutil.copyfileobj(response, handle, length=1 << 20)
        partial.replace(CKPT_PATH)

    size = CKPT_PATH.stat().st_size
    digest = sha256_file(CKPT_PATH)
    payload = {
        "path": str(CKPT_PATH),
        "url": CKPT_URL,
        "size_bytes": size,
        "sha256": digest,
        "sha256_expected": CKPT_SHA256,
        "matches": digest == CKPT_SHA256,
    }
    log_step("ckpt_sha", payload)
    if digest != CKPT_SHA256:
        fail("ckpt_sha", json.dumps(payload, indent=2))
    return payload


# ----------------------------------------------------------- step 2: registry
def register_mmdet3d_pipelines():
    """Register mmdet3d transforms without importing mmdet3d.datasets.__init__.

    Copied in spirit from ``tests/test_pipeline_e2e.py``: the package __init__
    pulls ``.nuscenes_dataset``, which needs nuscenes-devkit (absent here), but
    the pipeline modules only need mmcv + mmdet + mmdet3d.core.
    """
    import importlib
    import types

    import mmdet3d

    root = os.path.dirname(mmdet3d.__file__)
    packages = (
        ("mmdet3d.datasets", ("datasets",)),
        ("mmdet3d.datasets.pipelines", ("datasets", "pipelines")),
    )
    for name, parts in packages:
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [os.path.join(root, *parts)]
            sys.modules[name] = pkg

    datasets = sys.modules["mmdet3d.datasets"]
    if not hasattr(datasets, "pipelines"):
        datasets.pipelines = sys.modules["mmdet3d.datasets.pipelines"]
    if not hasattr(mmdet3d, "datasets"):
        mmdet3d.datasets = datasets

    # numba 0.58 dropped ``numba.errors`` while the vendored pipelines still
    # import it; alias the modern module.
    if "numba.errors" not in sys.modules:
        import numba.core.errors

        sys.modules["numba.errors"] = numba.core.errors

    importlib.import_module("mmdet3d.datasets.pipelines.formating")
    importlib.import_module("mmdet3d.datasets.pipelines.transforms_3d")


def setup_pipelines():
    # mmdet3d transforms first: ``spray.pipeline.install()`` runs at import time
    # and silently registers nothing if the mmdet3d pipeline modules cannot be
    # imported yet.
    register_mmdet3d_pipelines()

    import spray.pipeline as spray_pipeline

    import_side = sorted(spray_pipeline._INSTALLED)
    explicit = sorted(spray_pipeline.install())

    from mmdet.datasets.builder import PIPELINES

    expected = ("CleanPointsCollect3D", "CleanPointsFormatBundle3D")
    missing = [name for name in expected if name not in PIPELINES]
    payload = {
        "registered_at_import": import_side,
        "registered_on_call": explicit,
        "missing": missing,
    }
    log_step("pipelines", payload)
    if missing:
        fail("pipelines", json.dumps(payload, indent=2))
    return payload


# ------------------------------------------------------------- step 3: config
def _chain(leaf):
    """Files torchpack's ``Config.load(recursive=True)`` would merge, root first."""
    leaf = os.path.abspath(leaf)
    ext = os.path.splitext(leaf)[1]
    candidates = [leaf]
    while os.path.dirname(leaf) != leaf:
        leaf = os.path.dirname(leaf)
        candidates.append(os.path.join(leaf, "default" + ext))
    return [path for path in reversed(candidates) if os.path.exists(path)]


def _merge(destination, source):
    for key, value in source.items():
        if isinstance(value, dict):
            if not isinstance(destination.get(key), dict):
                destination[key] = {}
            _merge(destination[key], value)
        else:
            destination[key] = value
    return destination


class _DotDict(dict):
    """dict with attribute access, like torchpack's ``Config``."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _wrap(node):
    if isinstance(node, dict):
        return _DotDict((key, _wrap(value)) for key, value in node.items())
    if isinstance(node, list):
        return [_wrap(value) for value in node]
    return node


def _resolve(node, namespace, depth=0):
    """Evaluate ``${...}`` expressions the way mmdet3d's ``recursive_eval`` does."""
    if depth > 32:
        raise RuntimeError("config interpolation nested too deeply")
    if isinstance(node, dict):
        return {
            key: _resolve(value, namespace, depth + 1) for key, value in node.items()
        }
    if isinstance(node, list):
        return [_resolve(value, namespace, depth + 1) for value in node]
    if isinstance(node, str):
        text = node.strip()
        if text.startswith("${") and text.endswith("}"):
            # torchpack/mmdet3d eval the expression with the config as globals.
            value = eval(text[2:-1], {"__builtins__": {}}, namespace)  # noqa: S307
            return _resolve(value, namespace, depth + 1)
    return node


def _config_dict(node):
    """Convert to ``mmcv.ConfigDict`` so the head can use ``train_cfg.assigner``."""
    from mmcv import ConfigDict

    if isinstance(node, dict):
        return ConfigDict(
            (key, _config_dict(value)) for key, value in node.items()
        )
    if isinstance(node, list):
        return [_config_dict(value) for value in node]
    return node


def load_config(relative):
    """Resolve the vendor config chain the way ``tools/test.py`` does.

    ``mmcv.Config.fromfile`` only reads one file, but the pinned configs are
    fragments without ``_base_`` keys: the real chain is the ancestor
    ``default.yaml`` of every directory, merged root first, then ``${...}``
    expressions evaluated against the merged tree.  The evaluation needs
    attribute access (``${augment2d.resize[0]}``), hence the DotDict namespace;
    the result is converted to ``ConfigDict`` because ``TransFusionHead`` reads
    ``train_cfg.assigner`` as an attribute.
    """
    import yaml

    path = REPO / relative
    merged = {}
    files = _chain(str(path))
    for name in files:
        with open(name) as handle:
            _merge(merged, yaml.safe_load(handle) or {})

    resolved = _resolve(merged, _wrap(merged))
    return _config_dict(resolved), files


def choose_model_config():
    cfg, files = load_config(MODEL_CONFIG)
    fuser = cfg["model"].get("fuser")
    choice = {
        "ticket_path": MODEL_CONFIG,
        "chosen": MODEL_CONFIG,
        "chain": [os.path.relpath(name, str(REPO)) for name in files],
        "fuser": fuser,
        "reason": "ticket path already provides the fusion branch",
    }
    if fuser is None:
        alternate, alternate_files = load_config(FALLBACK_CONFIG)
        alternate_fuser = alternate["model"].get("fuser")
        if alternate_fuser is not None:
            choice.update(
                {
                    "chosen": FALLBACK_CONFIG,
                    "chain": [
                        os.path.relpath(name, str(REPO)) for name in alternate_files
                    ],
                    "fuser": alternate_fuser,
                    "reason": (
                        "ticket path resolves model.fuser=None; the vendor "
                        "README pairs bevfusion-det.pth with convfuser.yaml, "
                        "which adds only the ConvFuser block"
                    ),
                }
            )
            log_step("cfg_leaf", choice)
            return alternate, alternate_files, choice
    log_step("cfg_leaf", choice)
    return cfg, files, choice


def build(cfg):
    from mmdet3d.models import build_model

    model_cfg = copy.deepcopy(cfg["model"])
    train_cfg = cfg.get("train_cfg")
    test_cfg = cfg.get("test_cfg")

    info = {"init_cfg_disabled": False, "init_cfg_error": None}
    started = time.time()
    try:
        model = build_model(model_cfg, train_cfg=train_cfg, test_cfg=test_cfg)
    except Exception as exc:  # noqa: BLE001 - reported verbatim
        # The Swin backbone initialises from a GitHub-hosted Swin-Tiny file
        # (model.encoders.camera.backbone.init_cfg).  Every weight is replaced
        # by the fused checkpoint loaded next, so a failed download must not
        # sink the probe.  The flag is recorded so nobody mistakes this for the
        # pristine config.
        info["init_cfg_error"] = repr(exc)[:2000]
        retry_cfg = copy.deepcopy(model_cfg)
        retry_cfg["encoders"]["camera"]["backbone"]["init_cfg"] = None
        model = build_model(retry_cfg, train_cfg=train_cfg, test_cfg=test_cfg)
        info["init_cfg_disabled"] = True
    info["build_seconds"] = round(time.time() - started, 2)
    return model, info


# --------------------------------------------------------- step 4: checkpoint
def extract_state(ckpt):
    if not isinstance(ckpt, dict):
        return ckpt, "state_dict(passthrough)"
    for key in ("state_dict", "model"):
        value = ckpt.get(key)
        if isinstance(value, dict):
            return value, key
    return ckpt, "top_level"


def load_weights(model, payload):
    import torch

    ckpt = torch.load(str(CKPT_PATH), map_location="cpu")
    state, container = extract_state(ckpt)
    state = dict(state)
    top_level = sorted(ckpt.keys()) if isinstance(ckpt, dict) else []

    stripped = False
    if state and all(key.startswith("module.") for key in state):
        state = dict((key[len("module."):], value) for key, value in state.items())
        stripped = True

    own = model.state_dict()
    missing = sorted(set(own) - set(state))
    unexpected = sorted(set(state) - set(own))

    load_error = None
    try:
        # A shape mismatch still raises under strict=False in torch 1.10.
        result = model.load_state_dict(state, strict=False)
        missing = sorted(set(missing) | set(result.missing_keys))
        unexpected = sorted(set(unexpected) | set(result.unexpected_keys))
    except Exception as exc:  # noqa: BLE001 - reported verbatim
        load_error = repr(exc)[:2000]

    def non_parameter(key):
        return (
            key.startswith("_")
            or "optimizer" in key
            or key.endswith("num_batches_tracked")
        )

    unexpected_parameter_like = [key for key in unexpected if not non_parameter(key)]
    report = {
        "container": container,
        "top_level_keys": top_level,
        "module_prefix_stripped": stripped,
        "ckpt_num_keys": len(state),
        "model_num_keys": len(own),
        "missing": len(missing),
        "unexpected": len(unexpected),
        "missing_names": missing[:20],
        "unexpected_names": unexpected[:20],
        "unexpected_non_parameter": [
            key for key in unexpected if non_parameter(key)
        ][:20],
        "load_error": load_error,
    }
    log_step("ckpt_load", report, summary="missing=%d unexpected=%d" % (
        report["missing"], report["unexpected"]))
    return report, (not missing and not unexpected_parameter_like and not load_error)


# ------------------------------------------------------------- step 5: freeze
def freeze(model):
    from spray.freeze import (
        FROZEN_PREFIXES,
        FROZEN_SUBSTRINGS,
        TRAINABLE_PREFIXES,
        apply_freeze,
    )

    report = apply_freeze(model)
    frozen_names = list(report["frozen_names"])
    trainable_names = list(report["trainable_names"])

    def camera_name(name):
        return any(name.startswith(prefix) for prefix in FROZEN_PREFIXES) or any(
            sub in name for sub in FROZEN_SUBSTRINGS
        )

    off_design = [name for name in frozen_names if not camera_name(name)]

    def root(name):
        parts = name.split(".")
        return ".".join(parts[:2]) if len(parts) > 1 else parts[0]

    covered = set()
    for name in trainable_names:
        for prefix in TRAINABLE_PREFIXES:
            if name.startswith(prefix):
                covered.add(prefix)
    unused_prefixes = [
        prefix for prefix in TRAINABLE_PREFIXES if prefix not in covered
    ]

    frozen_roots = sorted(set(root(name) for name in frozen_names))
    trainable_roots = sorted(set(root(name) for name in trainable_names))

    payload = {
        "n_total_params": report["n_total_params"],
        "n_trainable_params": report["n_trainable_params"],
        "n_frozen": report["n_total_params"] - report["n_trainable_params"],
        "n_frozen_tensors": len(frozen_names),
        "len_unmatched": len(report["unmatched"]),
        "unmatched": list(report["unmatched"]),
        "unmatched_logged": list(report["unmatched"][:40]),
        "frozen_roots": frozen_roots,
        "trainable_roots": trainable_roots,
        "frozen_names_not_camera": off_design,
        "trainable_prefixes_used": sorted(covered),
        "trainable_prefixes_unused": unused_prefixes,
        "first_trainable": trainable_names[:8],
        "first_frozen": frozen_names[:8],
    }
    # The full unmatched list goes to probe.json; the log line carries at most
    # 40 names so a rename storm cannot bury the rest of the evidence.
    logged = dict(payload)
    logged["unmatched"] = payload["unmatched_logged"]
    log_step("freeze", logged)
    ok = bool(report["n_trainable_params"] > 0) and not off_design
    return payload, ok


# ------------------------------------------------------------- step 6: memory
def memory(freeze_payload, device):
    total = int(freeze_payload["n_total_params"])
    trainable = int(freeze_payload["n_trainable_params"])
    weights = total * FP32_BYTES
    grad = trainable * FP32_BYTES
    # AdamW keeps two fp32 moments per trainable tensor element.
    adam = 2 * trainable * FP32_BYTES
    payload = {
        "device": device,
        "dtype": "fp32",
        "n_total_params": total,
        "n_trainable_params": trainable,
        "weights_bytes": weights,
        "grad_bytes": grad,
        "adamw_state_bytes": adam,
        "total_bytes": weights + grad + adam,
        "weights_gb": round(weights / GIB, 4),
        "grad_gb": round(grad / GIB, 4),
        "adamw_state_gb": round(adam / GIB, 4),
        "total_gb": round((weights + grad + adam) / GIB, 4),
        "source": (
            "[DO] param counts read from the built model; 4 B/element fp32; "
            "AdamW = exp_avg + exp_avg_sq. No torch.cuda.max_memory_allocated "
            "(no forward in this ticket)."
        ),
        "step_time_measured_in": "ticket 11",
    }
    log_step("memory", payload)
    return payload


def main():
    started = time.time()
    print("PROBE_STEP env %s" % json.dumps({
        "python": sys.version.split()[0],
        "repo": str(REPO),
    }, sort_keys=True), flush=True)

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_step("device", {
        "device": device,
        "torch": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": getattr(torch.version, "cuda", None),
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
    })

    checkpoint = ensure_checkpoint()
    pipelines = setup_pipelines()

    cfg, files, choice = choose_model_config()
    model, build_info = build(cfg)
    model = model.to(device)
    model.eval()

    n_params = int(sum(param.numel() for param in model.parameters()))
    log_step("model", {
        "chosen_config": choice["chosen"],
        "config_files": choice["chain"],
        "build_seconds": build_info["build_seconds"],
        "init_cfg_disabled": build_info["init_cfg_disabled"],
        "init_cfg_error": build_info["init_cfg_error"],
        "n_total_params": n_params,
        "state_dict_keys": len(model.state_dict()),
        "device": device,
    })

    ckpt_report, ckpt_ok = load_weights(model, checkpoint)
    freeze_payload, freeze_ok = freeze(model)
    memory_payload = memory(freeze_payload, device)

    failures = []
    if not ckpt_ok:
        failures.append("ckpt_load")
    if not freeze_ok:
        failures.append("freeze")

    payload = {
        "ckpt_sha": checkpoint,
        "pipelines": pipelines,
        "cfg_leaf": choice,
        "ckpt_load": ckpt_report,
        "freeze": freeze_payload,
        "memory": memory_payload,
        "n_total_params": n_params,
        "device": device,
        "elapsed_s": round(time.time() - started, 1),
        "failures": failures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(str(OUT_JSON), "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)

    if failures:
        print("PROBE_FAILED %s" % ",".join(failures), flush=True)
        return 1

    print("PROBE_OK " + json.dumps({
        "ckpt_sha256": checkpoint["sha256"],
        "missing": ckpt_report["missing"],
        "unexpected": ckpt_report["unexpected"],
        "n_total_params": n_params,
        "n_trainable_params": freeze_payload["n_trainable_params"],
        "n_frozen_tensors": freeze_payload["n_frozen_tensors"],
        "unmatched": freeze_payload["unmatched"],
        "weights_gb": memory_payload["weights_gb"],
        "grad_gb": memory_payload["grad_gb"],
        "adamw_state_gb": memory_payload["adamw_state_gb"],
        "total_gb": memory_payload["total_gb"],
        "device": device,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
