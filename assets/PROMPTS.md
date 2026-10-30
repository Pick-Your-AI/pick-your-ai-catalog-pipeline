# Generated asset provenance

## assets/icon.png
- Date: 2026-10-30
- Tool and model: Codex CLI 0.164.0 built-in image generation (model id not reported by the tool)
- Seed: not supported
- Reference images: none
- Prompt (verbatim, attempt 2; selected):

```text
Use your image generation capability to create ONE image. Do not modify any other files.

NEON NIGHT REPO ICON · Pick-Your-AI/pick-your-ai-catalog-pipeline

Create one square 1024 × 1024 px image of a single repository glyph.
Use a simple geometric silhouette with a luminous outline and one accent spark.
Keep the background empty and the glyph inside the central 688 × 688 px square.
Size class SQUARE: a squarish glyph about 600 to 660 px on each side.

GLYPH: Catalog gate. Three stacked rounded rectangular slabs, each offset slightly from the one below like layered catalog records, topped by a tall arched gateway outline; one thin vertical line passes down through the arch into the stack, showing records admitted through a source-rights gate into a catalog.
SPARK PLACEMENT: One small filled diamond centered on the keystone at the top of the arch.
PALETTE: outline #0F766E, glow #14B8A6; one spark in #FBBF24.
The spark is the only filled shape and the only element in #FBBF24; keep the
glyph outline in #0F766E so the spark remains distinct at small sizes.

No text, letters, numbers, words, logos, brand marks, human figures or third-party IP.

Produce four candidates. Use the tool's default seed.
The lock pass renders assets/icon.png as a flat glyph in the family's light-surface
inks, without a tile or glow. Do not render the repository name in the image.

BACKGROUND: a perfectly flat, untextured solid #F8FAFC background filling the whole 1024 x 1024 image; no gradient, vignette, grid, floor, shadow or glow touching the edges. 10% empty margin on all sides; the glyph sits inside the central 688 x 688 px square.
ASPECT RATIO: square, 1:1.
STYLE: completely flat vector-like geometric line art, one uniform stroke weight, rounded corners, crisp hard edges. NO glow, NO soft shadow, NO gradients, NO haze, NO texture: every shape is a solid flat colour. Use only teal #0F766E for all lines (#14B8A6 may appear as a thin inner highlight only) and amber #FBBF24 for the single diamond spark. No blue.
NEGATIVE LIST: no text, letters, numbers, words, labels, logos, brand marks, watermarks, signatures; no people, faces or hands; no padlock, keyhole, shield or cloud; no database cylinder; no photorealism, textures or 3D rendering; no columns, pillars or pedestals; no extra objects beyond the slabs, the arch, the single line and the one diamond spark; every surface stays blank.

```


- Candidates: 2 generated. Attempt 1 (soft glow variant, Codex session 01a18b6c-ddae-75d0-8644-f88bfed8fae0) was rejected by `content icon normalize` with art-fail:icon-budget (624105 bytes > 300000). Attempt 2 (flat, no glow; session 01a18b6d-ea30-7651-99fa-cf49920cd303) selected (reason: clean teal and amber line art, no text, inside the live area).
- Post-processing: showcase.py 1.0.0 `content icon normalize --ground transparent` (keyed from #F5F7FA, lanczos, trim, fit to live area 168..856); output sha256 e2342047e79a92cb9a1b75708d0c9b9520a8f839529f8d8d27aa0fbb123fac9e; 121 KB
- Alt text: A teal line-art arched gateway with a vertical line down its centre and a small amber diamond at its keystone, standing on three stacked rounded slabs.
