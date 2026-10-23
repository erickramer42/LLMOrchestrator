"""Code snippets with a known answer, shared by the golden suite
(golden_tests.py) and the bake-off (eval_harness/bakeoff.py). Both send
them to a model as written, so an edit changes what those runs measure:
add a fixture instead of editing one."""

CANFD_BUFFER_OVERFLOW = (
    '// core/src/frame_decode.cpp\n'
    'void decode(const PASSTHRU_MSG* msg) {\n'
    '    uint8_t buf[8];\n'
    '    memcpy(buf, msg->DataSize);\n'
    '}')

ABI_TYPE_LEAK = (
    '// core/include/qttune/session.h  (public C ABI header)\n'
    '#include <vector>\n'
    '#include <string>\n'
    'extern "C" std::vector<std::string> qttune_get_session_names(qttune_session_t* s);')

CLEAN_ABI_HEADER = (
    '// core/include/qttune/init.h\n'
    '#pragma once\n'
    '#ifdef __cplusplus\nextern "C" {\n#endif\n'
    'typedef struct qttune_ctx qttune_ctx;\n'
    'int qttune_init(qttune_ctx** out);\n'
    'int qttune_shutdown(qttune_ctx* ctx);\n'
    '#ifdef __cplusplus\n}\n#endif')
