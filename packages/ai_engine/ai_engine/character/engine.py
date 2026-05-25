"""CharacterEngine — keep the same character looking the same across scenes.

Strategy (docs/ARCHITECTURE.md §4), layered weakest→strongest:
  1. Reference-image locking: pin one canonical image per character.
  2. IPAdapter: inject that reference's identity into every scene's generation
     (the main lever; works with the ComfyUI SDXL workflow).
  3. Face-embedding memory: compute an embedding (InsightFace) from the reference
     and *verify* generated frames, flagging low-similarity ones for regeneration.
  4. Optional per-character LoRA when the user has trained one.

`apply()` returns backend-agnostic kwargs the ImageBackend injects (ipadapter
image + weight, lora path/strength). Heavy deps (insightface, onnx) are lazy and
optional — if unavailable, the engine degrades to reference-lock + IPAdapter and
skips numeric verification rather than crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ai_engine.interfaces import Artifact, Character, CharacterEngine, GenerationConfig, Scene
from ai_engine.utils.logging import get_logger

log = get_logger("character")


class IPAdapterCharacterEngine(CharacterEngine):
    def __init__(self, *, ipadapter_weight: float = 0.7, verify_threshold: float = 0.5) -> None:
        self.ipadapter_weight = ipadapter_weight
        self.verify_threshold = verify_threshold
        self._registry: dict[str, Character] = {}
        self._face_app: Any = None  # lazily created InsightFace app, or None

    # --- registration ----------------------------------------------------- #
    def register(self, character: Character) -> Character:
        if character.reference_image is None:
            log.warning("character '%s' has no reference image; identity locking will be weak", character.name)
        else:
            character.face_embedding = self._embed(character.reference_image)
        self._registry[character.id] = character
        log.info("registered character '%s' (embedding=%s, lora=%s)",
                 character.name, character.face_embedding is not None, bool(character.lora_path))
        return character

    # --- per-scene application ------------------------------------------- #
    def apply(self, scene: Scene, characters: list[Character], cfg: GenerationConfig) -> dict[str, Any]:
        """Build the kwargs an ImageBackend needs to lock identity for this scene.
        Uses the first scene character that has a reference image."""
        relevant = [c for c in characters if c.id in scene.character_ids] or characters
        kwargs: dict[str, Any] = {}
        for char in relevant:
            if char.reference_image is not None:
                kwargs["ipadapter_image"] = str(char.reference_image)
                kwargs["ipadapter_weight"] = self.ipadapter_weight
            if char.lora_path is not None:
                kwargs["lora_path"] = str(char.lora_path)
                kwargs["lora_strength"] = 0.8
            break
        return kwargs

    # --- verification ----------------------------------------------------- #
    def verify(self, artifact: Artifact, character: Character) -> float:
        """Cosine similarity between the generated frame's face and the character's
        reference embedding. Returns 1.0 (skip) when face tooling is unavailable."""
        if character.face_embedding is None:
            return 1.0
        gen = self._embed(artifact.path)
        if gen is None:
            return 1.0
        score = self._cosine(gen, character.face_embedding)
        if score < self.verify_threshold:
            log.warning("scene %s face similarity %.2f < %.2f — candidate for regeneration",
                        artifact.scene_index, score, self.verify_threshold)
        return score

    # --- internals -------------------------------------------------------- #
    def _ensure_face_app(self) -> Any:
        if self._face_app is not None:
            return self._face_app
        try:
            from insightface.app import FaceAnalysis  # noqa: PLC0415

            app = FaceAnalysis(name="buffalo_l")
            app.prepare(ctx_id=0, det_size=(640, 640))
            self._face_app = app
        except Exception as exc:  # noqa: BLE001 - optional dependency / model download
            log.info("face embedding unavailable (%s); skipping numeric verification", exc)
            self._face_app = False  # sentinel: tried and failed
        return self._face_app

    def _embed(self, image_path: Path) -> Optional[Any]:
        app = self._ensure_face_app()
        if not app:
            return None
        try:
            import numpy as np  # noqa: PLC0415
            from PIL import Image  # noqa: PLC0415

            img = np.array(Image.open(image_path).convert("RGB"))[:, :, ::-1]  # RGB->BGR
            faces = app.get(img)
            return faces[0].normed_embedding if faces else None
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to embed %s: %s", image_path, exc)
            return None

    @staticmethod
    def _cosine(a: Any, b: Any) -> float:
        import numpy as np  # noqa: PLC0415

        a, b = np.asarray(a), np.asarray(b)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)
