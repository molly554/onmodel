---
name: shoot-brief
description: Prepare a brief for generating an on-model product photo with an image engine. Use when the user gives a product photo and wants a prompt, the risks to watch, and the resolution to use before they generate. It tags the product, assembles a starter prompt from the recipe rules, and says what to check afterwards. It does not generate images.
---

# Shoot brief

Turn a product photo into a brief: what kind of product it is, which parts of it are easy to get wrong, a starter prompt for a "swap the product" generation, and what to check afterwards. The recipe rules are in `references/recipes.md`.

## What you need

- The product photo.
- Optionally the pose reference photo the user will give the engine (a person posing with some other product or outfit).

## Steps

1. Look at the product photo and decide:
   - the sub-category (Tops, Outerwear, Dresses and skirts, Pants, Necklaces, Earrings, Rings, Bracelets, Lipstick, Base and skincare, Eyeshadow palettes);
   - whether the person will **wear** or **hold** it;
   - the risk tags that apply (`text`, `glass`, `metal`, `gem`, `lace`, `black`, `pattern`, `multi`, `hand`, `worn_hand`, `person_in_photo`). The table in `references/recipes.md` says when each applies;
   - the separate parts that must all appear (for example a tube, a cap and a retail card), and any printed text, line by line.
2. Assemble the prompt: the header with the verb, then the v1 lead, then one rule per tag in the order of the table, then the always rule. If the user wants the plain generic prompt, use the v0 tail instead.
3. Add anything the product needs that the rules do not say: the exact color name, the list of parts, the real dimensions.
4. Give the brief in this shape:
   - **Product:** sub-category, wear or hold, tags
   - **Watch for:** the two or three things most likely to go wrong for this product
   - **Prompt:** the assembled prompt in a code block, ready to paste. Say that Image 1 is the product photo and Image 2 is the pose reference
   - **Settings:** if the product carries small print, render at 2K or higher
   - **Afterwards:** check the result with the `fidelity-check` skill (or `onmodel check`) before it is published

## Rules

- Use the rules from `references/recipes.md`; do not invent new rules or promise that a rule fixes a problem. They are a tested baseline, not a guarantee.
- If the product carries text, say plainly that engines often garble small print, and that a repair pass or a higher resolution may be needed.
- Do not state outcomes ("this will give a faithful photo"). Say what to check.
- Use only pose references the user has the right to use. If a pose reference shows a real person, remind the user that they need that person's consent.

Source and the benchmark: https://github.com/molly554/onmodel
