"""The vocabulary of the rubric: checklist items, answers, defect codes, risk tags.

Everything else (scoring, prompts, schemas, docs) is checked against this module, so a code is defined once.
"""
from __future__ import annotations

# The nine questions a reviewer answers about one result photo. The first five make up the product-fidelity dimension.
FIDELITY_ITEMS = ("shape", "color", "material", "text", "parts")
OTHER_ITEMS = ("pose", "identity", "artifacts", "scale")
ITEMS = FIDELITY_ITEMS + OTHER_ITEMS
DIMENSIONS = ("fidelity", "pose", "identity", "artifacts", "scale")

QUESTIONS = {
    "shape": "Does the product have the same silhouette, proportions and construction details as in the real product photo?",
    "color": "Does the product have the same hue, saturation and brightness (including how dark black stays)?",
    "material": "Does the product have the same finish and texture (glass transparency, metal reflections, lace, fabric or print pattern)?",
    "text": "Is every printed word, letter, number and logo identical to the real product, character by character? (No text on the product: same.)",
    "parts": "Does the photo show the same parts as the real product: none missing, none extra, none merged?",
    "pose": "Does the result follow the pose reference's pose, framing and camera angle?",
    "identity": "Is the person the same as in the pose reference (or the chosen model), and is no hand, mannequin or person from the product photo carried in?",
    "artifacts": "Is the photo free of anatomy errors (five fingers per hand), deformation, stray text, watermarks and melted objects?",
    "scale": "Is the product's real-world size right relative to the body or a reference object? (Not applicable when size cannot be judged.)",
}

# same / not_applicable = nothing wrong. minor = visible but not damaging. different = clearly wrong.
# cannot_tell = the reviewer could not see enough; it is never treated as "same".
ANSWERS = ("same", "minor", "different", "cannot_tell", "not_applicable")

# code -> (checklist item it belongs to, veto?, meaning, advice)
DEFECTS: dict[str, dict] = {
    "WRONG_PRODUCT":       {"item": "shape",     "veto": True,  "meaning": "A different product from the real one.", "advice": "Check that the product photo is the main image and shows the product clearly."},
    "SHAPE_OFF":           {"item": "shape",     "veto": False, "meaning": "Silhouette or construction details differ.", "advice": "Use a cleaner, straight-on product photo; add a second angle."},
    "LENGTH_DRIFT":        {"item": "shape",     "veto": False, "meaning": "Hem or length follows the pose reference instead of the product.", "advice": "Choose a pose reference whose garment has the same length."},
    "COLOR_OFF":           {"item": "color",     "veto": False, "meaning": "Shade or saturation shifted, same color family.", "advice": "Name the exact color in the prompt and check the product photo's white balance."},
    "COLOR_FAMILY":        {"item": "color",     "veto": True,  "meaning": "Wrong color family.", "advice": "Name the exact color in the prompt and check the product photo's white balance."},
    "MATERIAL_OFF":        {"item": "material",  "veto": False, "meaning": "Finish or texture differs (glass, metal, lace, print).", "advice": "Add the material rule for this product's tag to the recipe."},
    "TEXT_GARBLE":         {"item": "text",      "veto": False, "meaning": "Small print is gibberish or unreadable.", "advice": "Render at 2K or higher and keep the label facing the camera."},
    "TEXT_WRONG":          {"item": "text",      "veto": True,  "meaning": "A large word or logo is wrong, missing or invented.", "advice": "Render at 2K, face the label to the camera, and run a repair pass for the text."},
    "LABEL_OCCLUDED":      {"item": "text",      "veto": False, "meaning": "Fingers or props cover the printed text.", "advice": "Choose a pose where the fingers stay off the label."},
    "PART_MISSING":        {"item": "parts",     "veto": True,  "meaning": "A part of the product is missing.", "advice": "List every piece in the prompt (for example 'one tube, one cap, one retail card')."},
    "PART_MERGED":         {"item": "parts",     "veto": True,  "meaning": "Two parts were merged into one.", "advice": "List every piece in the prompt."},
    "PART_EXTRA":          {"item": "parts",     "veto": True,  "meaning": "A part that the product does not have was added.", "advice": "State 'no extra parts' and list the pieces."},
    "POSE":                {"item": "pose",      "veto": False, "meaning": "Pose or framing differs from the reference.", "advice": "Use a clearer pose reference or lower the number of references."},
    "IDENTITY":            {"item": "identity",  "veto": False, "meaning": "The person differs from the reference or the chosen model.", "advice": "Check the model card or pose reference, and avoid mixing several people."},
    "LEAK_HAND_MANNEQUIN": {"item": "identity",  "veto": True,  "meaning": "A hand, mannequin or person from the product photo appears in the result.", "advice": "Add a 'do not copy hands, mannequins or props from Image 1' rule, or crop the product photo."},
    "ARTIFACT":            {"item": "artifacts", "veto": False, "meaning": "Anatomy error, stray text, watermark or melted object.", "advice": "Regenerate; check that the pose reference has no artifacts of its own."},
    "SEVERE_DEFORMITY":    {"item": "artifacts", "veto": True,  "meaning": "A severe deformity of the product or the body.", "advice": "Regenerate; check that the pose reference has no artifacts of its own."},
    "SCALE_OFF":           {"item": "scale",     "veto": False, "meaning": "The product looks too big or too small for the body.", "advice": "Add a size reference or the product's real dimensions to the prompt."},
}
VETO_CODES = tuple(c for c, d in DEFECTS.items() if d["veto"])

# What the rules and the recipes can condition on.
RISK_TAGS = ("text", "glass", "metal", "gem", "lace", "black", "pattern", "multi", "hand", "worn_hand", "person_in_photo")

# The public sub-categories of the starter recipes.
SUBCATEGORIES = (
    "Tops", "Outerwear", "Dresses and skirts", "Pants",
    "Necklaces", "Earrings", "Rings", "Bracelets",
    "Lipstick", "Base and skincare", "Eyeshadow palettes",
)
