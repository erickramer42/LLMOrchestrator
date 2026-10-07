"""file_metadata.py — file-to-layer mapping for context-aware review.
Injects layer metadata into review transcripts so the reviewer knows
which rules apply to which file paths. Layer rules match QtTune's
actual repo layout (core/ = strict, app/ = Qt-allowed bridge)."""

import re

def identify_layer(file_path: str) -> str:
    """Return layer name for a path, using substring search (handles
    both '+++ b/app/foo.cpp' diff headers and '// core/src/x.cpp'
    comment lines)."""
    if not file_path:
        return "unknown"
    p = file_path.lower().replace("\\", "/")
    if re.search(r"(^|/)core/", p):
        return "core"
    if "bridge" in p or re.search(r"(^|/)app/", p):
        return "bridge"
    if re.search(r"(^|/)(ui|qml|gui)/", p):
        return "app"
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
