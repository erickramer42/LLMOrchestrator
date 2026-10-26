"""file_metadata.py — file-to-layer mapping for context-aware review.
Injects layer metadata into review transcripts so the reviewer knows
which rules apply to which file paths. Layer rules match QtTune's
actual repo layout (core/ = strict, app/ = Qt-allowed bridge)."""

import re

# A directory name must start the string or follow '/' or whitespace,
# so '// core/src/x.cpp' comment lines match but 'hardcore/' does not.
_DIR = r"(^|[/\s])"


def identify_layer(file_path: str) -> str:
    """Return layer name for a path, using substring search (handles
    both '+++ b/app/foo.cpp' diff headers and '// core/src/x.cpp'
    comment lines).

    Order matters: core is strictest and wins; UI directories and .qml
    files are checked before the app/ bridge rule, because QtTune keeps
    its QML under app/qml/."""
    if not file_path:
        return "unknown"
    p = file_path.lower().replace("\\", "/")
    if re.search(_DIR + r"core/", p):
        return "core"
    if re.search(_DIR + r"(ui|qml|gui)/", p) or re.search(r"\.qml\b", p):
        return "app"
    if "bridge" in p or re.search(_DIR + r"app/", p):
        return "bridge"
    return "unknown"

def get_layer_constraints(layer: str) -> str:
    """Human-readable constraints for the identified layer."""
    if layer == "core":
        return ("FILE LAYER: core (strictest)\n"
                "- NO Qt headers allowed — flag any Qt include as a blocker\n"
                "- All boundary functions must use extern \"C\"\n"
                "- Structs must be POD; handles opaque\n"
                "- Buffer assumptions: 8-byte CAN vs 64+ CAN-FD")
    elif layer == "bridge":
        return ("FILE LAYER: bridge (Qt ALLOWED)\n"
                "- Qt headers ARE permitted — this is the Qt integration layer.\n"
                "  Do NOT flag Qt includes (QString, QAbstractListModel, etc.)\n"
                "  as Qt-leakage blockers in bridge files.\n"
                "- Core ABI rules still apply to C-boundary calls (qttune_*)\n"
                "- Thread-safety requirements are ACTIVE (worker/GUI threads)")
    elif layer == "app":
        return ("FILE LAYER: app (least restricted)\n"
                "- Qt fully permitted\n"
                "- Focus on UI patterns, lifecycle, performance")
    return "FILE LAYER: unknown — apply all rules conservatively"


# v16 (ADR-0002, twenty-first measurement): a diff whose files fall in
# several layers gets each file's layer, then each layer's rules once,
# strictest first. Before it, only the first file's note was sent.
LAYER_ORDER = ("core", "bridge", "app", "unknown")
LAYER_MAP_HEADER = ("FILE LAYERS: this diff changes files in {count} layers; "
                    "each file's rules apply to that file only.\n")


def layer_note_for(paths) -> tuple:
    """(note, template) for the files a review covers. One layer, or no
    path, gives that layer's note unchanged; several give the per-file
    map. template is the note without its paths, for the fingerprint."""
    layers = [identify_layer(p) for p in paths] or ["unknown"]
    present = [layer for layer in LAYER_ORDER if layer in layers]
    blocks = "\n".join(get_layer_constraints(layer) for layer in present)
    if len(present) == 1:
        return blocks, blocks
    listing = "".join(f"- {p}: {layer}\n" for p, layer in zip(paths, layers))
    return (LAYER_MAP_HEADER.format(count=len(present)) + listing + blocks,
            LAYER_MAP_HEADER + blocks)
