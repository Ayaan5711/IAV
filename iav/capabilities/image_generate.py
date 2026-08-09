"""Generate Image — structured prompt → new exam-question image.

Unlike image_enhance (which edits an SME's existing sketch), this generates
an image from nothing: assessment metadata + media-specific attributes
assembled into one prompt, sent straight to Nano Banana with no input image.
"""

from __future__ import annotations

import json
import logging
import string

from iav.capabilities._json_utils import JsonParseError, parse_json_loose
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.capabilities.prompt_schema import (
    CommonAttributes,
    assessment_outcome_line,
    common_block,
    language_instruction_suffix,
    validate_common_attributes,
    validate_free_text,
)
from iav.models import image_generation
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.models.text_generation import TextGenerationError, generate_text
from iav.storage import save_output

logger = logging.getLogger(__name__)


class ImageGenerateError(RuntimeError):
    """Raised when image generation cannot produce an output."""


def _format_label_scheme_for_render(labels: list[dict]) -> str:
    """Formats the label scheme for the *image* model -- placeholders need
    their concept described so the model knows where/how to draw the tag,
    while never printing that concept as text.

    Deliberately avoids putting the words "given"/"placeholder" directly
    next to each id as an all-caps category marker: in testing, the image
    model echoed those exact words (and a placeholder's concept name) into
    the rendered image as literal visible text instead of treating them as
    instructions -- e.g. drawing the word "PLACEHOLDER" itself where a bare
    tag letter should go. Grouping each kind under a single section header
    (stated once, not per line) removes that pattern instead of just telling
    the model not to copy it.
    """
    given_lines = [
        f'- {item.get("id", "?")}: draw the text "{item.get("value", "")}" here, nothing else'
        for item in labels if item.get("kind") == "given"
    ]
    placeholder_lines = [
        f'- {item.get("id", "?")}: place this at the part that is anatomically/conceptually the '
        f'{item.get("concept", "")} -- draw ONLY the single character "{item.get("id", "?")}" here, '
        f'never the words "{item.get("concept", "")}"'
        for item in labels if item.get("kind") == "placeholder"
    ]
    parts = []
    if given_lines:
        parts.append(
            "Parts that show their real name -- draw exactly the quoted text at each, nothing more:\n"
            + "\n".join(given_lines)
        )
    if placeholder_lines:
        parts.append(
            "Parts that show ONLY a bare tag letter -- draw nothing but that single letter at each, "
            "no words, no descriptions:\n" + "\n".join(placeholder_lines)
        )
    return "\n\n".join(parts)


def _format_placeholder_scheme_for_questions(labels: list[dict]) -> str:
    """Placeholder entries only, worded as an answer key for the *question*
    model -- it never sees the image, so there's nothing left to re-guess.
    """
    return "\n".join(
        f'- {item.get("id", "?")}: {item.get("concept", "")}'
        for item in labels
        if item.get("kind") == "placeholder"
    )


def _assign_label_ids(labels: object) -> None:
    """Assigns short, sequential ids (A, B, C, ...) to each label in place,
    instead of asking the model to invent them.

    Left to invent its own "short unique id", the label-design model has
    been observed either reusing the same tag for every entry (especially
    when the description hints at a specific labelling style like "a, b,
    c") or hallucinating nonsense strings ("ssc", "bshbdh") once asked to
    keep them short. Assigning ids ourselves, in the order the model listed
    the entries, makes both failure modes structurally impossible rather
    than something a prompt has to talk the model out of.
    """
    if not isinstance(labels, list):
        return
    letters = string.ascii_uppercase
    for i, item in enumerate(labels):
        if not isinstance(item, dict):
            continue
        item["id"] = letters[i] if i < len(letters) else letters[i // len(letters) - 1] + letters[i % len(letters)]


def _validate_label_scheme(labels: object) -> list[str]:
    """Programmatic checks on the label-design step's output -- catches a
    bad/duplicate id before it reaches the image render or the questions,
    rather than trusting the model's "never reuse an id" instruction alone.
    """
    if not isinstance(labels, list) or not labels:
        return ["Label design returned no labels."]

    errors: list[str] = []
    seen_ids: set[str] = set()
    has_placeholder = False
    for item in labels:
        if not isinstance(item, dict):
            errors.append(f"Label entry is not an object: {item!r}")
            continue
        lid = item.get("id")
        if not isinstance(lid, str) or not lid.strip():
            errors.append(f"Label entry has no valid 'id': {item!r}")
            continue
        if lid in seen_ids:
            errors.append(f"Duplicate label id '{lid}' -- every id must be unique.")
        seen_ids.add(lid)

        kind = item.get("kind")
        if kind == "given":
            value = item.get("value")
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Label '{lid}' is 'given' but has no value to render.")
        elif kind == "placeholder":
            has_placeholder = True
            concept = item.get("concept")
            if not isinstance(concept, str) or not concept.strip():
                errors.append(f"Label '{lid}' is 'placeholder' but has no concept for the answer key.")
        else:
            errors.append(f"Label '{lid}' has an invalid 'kind' ({kind!r}); must be 'given' or 'placeholder'.")

    if not has_placeholder:
        errors.append("No 'placeholder' labels were designed -- nothing for the questions to ask about.")
    return errors


class ImageGenerate(Capability):
    name = "image_generate"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def _run_label_design(
        self, prompt: str, model: str, *, azure_deployment: str | None, engine: str
    ) -> tuple[list[dict], dict]:
        """One label-design attempt: call, parse, return (labels, call_record).

        Pure text in/out (no image bytes involved yet), so this goes through
        the same Auto/Gemini/Azure text dispatcher every other text-only step
        in the app uses -- it should follow the selected vendor exactly like
        text generation does elsewhere, not be hardcoded to Gemini.

        Raises on a hard failure (no text / bad JSON) -- validating the
        *content* (unique ids, complete entries) happens separately in the
        caller, which decides whether to retry.
        """
        try:
            design_result = generate_text(
                gemini_client=self.client, gemini_model=model, prompt=prompt,
                label="design_labels", azure_deployment=azure_deployment, engine=engine,
                response_mime_type="application/json",
            )
        except (GeminiCallError, TextGenerationError) as exc:
            raise ImageGenerateError(f"Label design failed: {exc}") from exc
        call_record = design_result.call_record

        design_raw = design_result.text.strip()
        if not design_raw:
            raise ImageGenerateError("Label design returned no text.")
        try:
            design_parsed = parse_json_loose(design_raw)
        except JsonParseError as exc:
            raise ImageGenerateError(str(exc)) from exc

        labels = design_parsed.get("labels") if isinstance(design_parsed, dict) else None
        if not isinstance(labels, list) or not labels:
            raise ImageGenerateError("Label design returned no usable labels.")
        _assign_label_ids(labels)
        return labels, call_record

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        free_text = (payload.text or payload.instruction or "").strip()
        params = payload.params or {}
        common = CommonAttributes(
            assessment_outcome=params.get("assessment_outcome", ""),
            difficulty_level=params.get("difficulty_level", "medium"),
            target_audience=params.get("target_audience", "undergraduate"),
            question_type=params.get("question_type", "mcq"),
        )
        visual_type = params.get("visual_type") or self._settings["visual_types"][0]
        style = params.get("style") or self._settings["styles"][0]

        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if errors:
            raise ValueError("; ".join(errors))

        model = params.get("model") or self._settings["model"]
        resolution = params.get("resolution") or self._settings.get("resolution")
        output_format = params.get("output_format") or self._settings.get("output_format")
        want_questions = bool(params.get("generate_questions", False))
        question_model = params.get("question_model") or self._settings.get("question_model", model)
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")
        language = params.get("language") or self.config.languages.get("default_output_language", "Same as input")
        use_label_placeholders = bool(params.get("use_label_placeholders", False))
        # Text-only steps (label design, question generation) -- separate
        # from image_engine below, which only governs the Images API
        # generate/edit call. This one follows azure_openai.default_deployment
        # (the chat/text deployment), not the image deployment.
        azure_deployment = self.config.azure_openai.get("default_deployment")
        engine = params.get("engine", "auto")
        prompt = self._settings["prompt_template"].format(
            visual_type=visual_type,
            style=style,
            common_block=common_block(common),
            free_text=free_text,
        )

        calls: list[dict] = []
        labels: list[dict] | None = None
        label_json_path = None

        if use_label_placeholders:
            design_prompt = self._settings["label_design_instruction"].format(
                free_text=free_text, common_block=common_block(common)
            )
            logger.info("image_generate: designing label scheme before rendering (engine=%s)", engine)
            labels, design_call = self._run_label_design(
                design_prompt, question_model, azure_deployment=azure_deployment, engine=engine
            )
            calls.append(design_call)

            label_errors = _validate_label_scheme(labels)
            if label_errors:
                logger.warning(
                    "image_generate: label design had %d issue(s), retrying once: %s",
                    len(label_errors), "; ".join(label_errors),
                )
                retry_prompt = design_prompt + (
                    "\n\nYour previous attempt had these problems -- fix them exactly:\n"
                    + "\n".join(f"- {e}" for e in label_errors)
                )
                labels, retry_call = self._run_label_design(
                    retry_prompt, question_model, azure_deployment=azure_deployment, engine=engine
                )
                retry_call["label"] = "design_labels_retry"
                calls.append(retry_call)
                label_errors = _validate_label_scheme(labels)
                if label_errors:
                    raise ImageGenerateError(
                        "Label design still has problems after a retry: " + "; ".join(label_errors)
                    )

            prompt = prompt + "\n\n" + self._settings["label_render_instruction"].format(
                label_summary=_format_label_scheme_for_render(labels)
            )
            label_bytes = json.dumps({"labels": labels}, indent=2, ensure_ascii=False).encode("utf-8")
            label_json_path = save_output(data=label_bytes, suffix=".json", capability=f"{self.name}-labels")

        azure_image_deployment = self.config.azure_openai.get("image_deployment")
        image_engine = params.get("image_engine", "auto")

        logger.info(
            "image_generate: model=%s visual_type=%s style=%s resolution=%s label_placeholders=%s "
            "image_engine=%s text_engine=%s",
            model, visual_type, style, resolution, use_label_placeholders, image_engine, engine,
        )

        try:
            result = image_generation.generate_image(
                gemini_client=self.client,
                gemini_model=model,
                prompt=prompt,
                label="image_generate",
                resolution=resolution,
                output_mime_type=output_format,
                azure_deployment=azure_image_deployment,
                engine=image_engine,
            )
        except image_generation.ImageGenerationError as exc:
            hint = (
                " (Azure image generation isn't available in this environment -- check 'Allow "
                "Gemini for image generation' above if you want Gemini to handle this step instead.)"
                if image_engine == "azure"
                else " (a Gemini failure here typically means a safety filter blocked the output.)"
            )
            raise ImageGenerateError(f"{exc}{hint}") from exc

        image_mime_type = result.image_mime_type
        suffix = ".jpg" if image_mime_type == "image/jpeg" else ".png"
        output_path = save_output(data=result.image_bytes, suffix=suffix, capability=self.name)

        calls.append(result.call_record)

        questions: list | None = None
        parsed: dict | None = None
        json_path = None
        question_engine: str | None = None
        if want_questions:
            # Placeholder entries carry their own answer key -- grounding the
            # question call in that key (no image bytes needed) instead of
            # having it re-derive labels by looking at the rendered picture,
            # which is what caused duplicate/mismatched labels before.
            placeholder_entries = [item for item in labels if item.get("kind") == "placeholder"] if labels else []
            if placeholder_entries:
                q_prompt = self._settings["placeholder_questions_instruction"].format(
                    question_type=qtype,
                    placeholder_summary=_format_placeholder_scheme_for_questions(labels),
                    assessment_outcome_line=assessment_outcome_line(common),
                ) + language_instruction_suffix(language)
                logger.info(
                    "image_generate: generating questions from the label answer key "
                    "(%d placeholders, language=%s, engine=%s)",
                    len(placeholder_entries), language, engine,
                )
                try:
                    q_result = generate_text(
                        gemini_client=self.client, gemini_model=question_model, prompt=q_prompt,
                        label="generate_questions", azure_deployment=azure_deployment, engine=engine,
                        response_mime_type="application/json",
                    )
                except (GeminiCallError, TextGenerationError) as exc:
                    raise ImageGenerateError(f"Question generation failed: {exc}") from exc
            else:
                q_prompt = self._settings["questions_instruction"].format(
                    count=count, question_type=qtype, level=level,
                    assessment_outcome_line=assessment_outcome_line(common),
                    visual_type=visual_type, free_text=free_text,
                ) + language_instruction_suffix(language)
                logger.info(
                    "image_generate: generating questions from the image (language=%s, engine=%s)",
                    language, engine,
                )
                try:
                    q_result = image_generation.understand_image(
                        gemini_client=self.client, gemini_model=question_model,
                        image_bytes=result.image_bytes, image_mime_type=image_mime_type,
                        instruction=q_prompt, label="generate_questions",
                        response_mime_type="application/json",
                        azure_deployment=azure_deployment, engine=engine,
                    )
                except image_generation.ImageGenerationError as exc:
                    raise ImageGenerateError(f"Question generation failed: {exc}") from exc
            calls.append(q_result.call_record)
            question_engine = q_result.engine

            q_raw = (q_result.text or "").strip()
            if not q_raw:
                raise ImageGenerateError("Model returned no question text.")
            try:
                parsed = parse_json_loose(q_raw)
            except JsonParseError as exc:
                raise ImageGenerateError(str(exc)) from exc

            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list) or not questions:
                raise ImageGenerateError("Model returned no usable questions.")

            json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
            json_path = save_output(data=json_bytes, suffix=".json", capability=f"{self.name}-questions")

        cost = summarize_costs(calls, self.config.pricing)

        logger.info("image_generate: wrote %s, est. cost $%.6f", output_path, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            text="",
            data=parsed,
            metadata={
                "model": model,
                "image_engine": result.engine,
                "revised_prompt": result.revised_prompt,
                "visual_type": visual_type,
                "style": style,
                "prompt": prompt,
                "output_bytes": len(result.image_bytes),
                "mime_type": image_mime_type,
                "generate_questions": want_questions,
                "question_count": len(questions) if questions else 0,
                "question_language": language,
                "question_engine": question_engine,
                "questions_json_path": str(json_path) if json_path else None,
                "use_label_placeholders": use_label_placeholders,
                "label_count": len(labels) if labels else 0,
                "label_json_path": str(label_json_path) if label_json_path else None,
                "cost": cost,
            },
        )
