"""Deterministic tests for repo_context retrieval (build_context_pack)
and the queued-connection call-site harvester. No network, no Ollama."""

import unittest

import repo_context as rc


class HarvestCallsites(unittest.TestCase):
    def test_detects_queued_connect(self):
        src = """
void Worker::setup() {
    // hand off to GUI thread
    connect(this, &Worker::frameReady,
            this, &Worker::onFrameReady, Qt::QueuedConnection);
}
"""
        sites = rc.harvest_callsites(src, "app/worker.cpp")
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0]["file"], "app/worker.cpp")
        self.assertIn("Qt::QueuedConnection", sites[0]["snippet"])
        self.assertEqual(sites[0]["line"], 4)
        self.assertEqual(sites[0]["doc"], "hand off to GUI thread")

    def test_blocking_variant_detected(self):
        src = "invokeMethod(obj, SLOT(run()), Qt::BlockingQueuedConnection);"
        self.assertEqual(len(rc.harvest_callsites(src, "a.cpp")), 1)

    def test_direct_connection_ignored(self):
        src = "connect(a, SIGNAL(x()), b, SLOT(y()));"
        self.assertEqual(len(rc.harvest_callsites(src, "a.cpp")), 0)

    def test_commented_out_call_ignored(self):
        src = "// connect(this, s1, this, s2, Qt::QueuedConnection);\nint x;"
        self.assertEqual(len(rc.harvest_callsites(src, "a.cpp")), 0)

    def test_long_multiline_lambda_connect(self):
        body = "\n".join(f"        auto tmp{i} = compute_something({i});"
                         for i in range(30))
        src = (f"connect(this, &Worker::frameReady, this,\n"
               f"        [this](const qttune_frame_t& f) {{\n{body}\n"
               f"        }}, Qt::QueuedConnection);\nint x;")
        sites = rc.harvest_callsites(src, "app/worker.cpp")
        self.assertEqual(len(sites), 1)
        # Check the snippet starts with connect AND contains QueuedConnection
        self.assertIn("connect(this, &Worker::frameReady", sites[0]["snippet"])
        self.assertIn("Qt::QueuedConnection", sites[0]["snippet"])
        # Allow either full or truncated representation
        self.assertTrue(");" in sites[0]["snippet"] or " ... " in sites[0]["snippet"])
        self.assertEqual(sites[0]["line"], 1)

class BuildContextPack(unittest.TestCase):
    INDEX = {
        "files": [
            {"path": "app/qttunebridge.cpp",
             "purpose": "Bridge between C core and QML UI",
             "layer": "bridge"},
            {"path": "core/src/codec.c",
             "purpose": "CAN frame decoding",
             "layer": "core"},
        ],
        "types": [
            {"name": "qttune_frame_t", "kind": "struct",
             "members": ["data", "data_length"], "def_file": "core/include/qttune.h"},
        ],
        "constants": [
            {"name": "MAX_FRAMES", "value": "512", "kind": "const",
             "file": "app/qttunebridge.cpp"},
        ],
        "callsites": [
            {"file": "app/qttunebridge.cpp", "line": 42,
             "snippet": "connect(worker, &Worker::frameReady, this, "
                        "&Bridge::handleFrameInternal, Qt::QueuedConnection);",
             "doc": None},
            {"file": "app/other.cpp", "line": 7,
             "snippet": "connect(w, s1, g, s2, Qt::QueuedConnection);",
             "doc": None},
        ],
    }

    DIFF = """diff --git a/app/qttunebridge.cpp b/app/qttunebridge.cpp
+++ b/app/qttunebridge.cpp
@@ -100,3 +100,10 @@
+void onFrame(const qttune_frame_t* frame) {
+  m_currentFrameCount++;
+}"""

    def test_retrieves_modified_file_and_callsite(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX)
        self.assertIn("qttunebridge.cpp", text)
        self.assertIn("Bridge between C core and QML UI", text)
        # the queued connection relevant to the modified file
        self.assertIn("handleFrameInternal", text)
        # but NOT the call site from an unrelated file
        self.assertNotIn("app/other.cpp", text)
        self.assertIsNone(report["error"])
        self.assertEqual(report["sections"]["modified_files"], 1)
        self.assertEqual(report["sections"]["call_sites"], 1)

    def test_referenced_type_pulled_in(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX)
        self.assertIn("qttune_frame_t", text)
        self.assertEqual(report["sections"]["types"], 1)

    def test_budget_enforced(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX,
                                             budget=50)
        self.assertLessEqual(len(text), 70)  # marker allowance
        self.assertEqual(report["used"], 50)
        self.assertIn("truncated", text.lower())

    def test_missing_index_fails_visible_not_fatal(self):
        text, report = rc.build_context_pack(self.DIFF, {})
        self.assertEqual(text, "")
        self.assertIsNotNone(report["error"])

    def test_empty_diff_gives_empty_sections(self):
        text, report = rc.build_context_pack("", self.INDEX)
        self.assertIsNone(report["error"])
        self.assertEqual(report["sections"]["modified_files"], 0)

    def test_no_matches_gives_no_pack(self):
        # A bare "GROUND TRUTH" header with no facts under it is noise.
        text, report = rc.build_context_pack("+++ b/docs/unindexed.md\n+hello",
                                             self.INDEX)
        self.assertEqual(text, "")
        self.assertEqual(report["entries"], 0)


# ============ code review 2026-10-21, finding 3: identifier matching ============

class IdentifierMatching(unittest.TestCase):
    def test_all_identifier_styles_are_collected(self):
        ids = rc._referenced_identifiers(
            "+ if (n > MAX_FRAMES || n > kMaxFrames) { snake_type_t t; }")
        self.assertTrue({"MAX_FRAMES", "kMaxFrames", "snake_type_t"} <= ids)

    def test_all_caps_constant_is_retrieved(self):
        diff = BuildContextPack.DIFF + "\n+  if (n > MAX_FRAMES) return;"
        text, report = rc.build_context_pack(diff, BuildContextPack.INDEX)
        self.assertIn("MAX_FRAMES = 512", text)
        self.assertEqual(report["sections"]["constants"], 1)

    def test_english_words_match_nothing(self):
        index = dict(BuildContextPack.INDEX,
                     types=[{"name": "The", "kind": "alias", "members": []}])
        # 'The' is only retrieved if the diff mentions an indexed name 'The',
        # which is fine: matching is exact intersection, not a heuristic.
        text, _ = rc.build_context_pack("+++ b/x.c\n+// nothing here", index)
        self.assertEqual(text, "")


# ============ code review 2026-10-21, finding 4: presentation fidelity ============

class CallsiteRendering(unittest.TestCase):
    SRC = """
void Bridge::onFrame(const qttune_frame_t* f) {
    QMetaObject::invokeMethod(self, [self, copy]() {
        // A long explanatory comment that used to fill the snippet window
        // and push the connection type out of view in the context pack.
        self->m_inFlightFrames.fetch_sub(1, std::memory_order_relaxed);
        if (copy.ok()) { self->handleFrameInternal(&copy); }
    }, Qt::QueuedConnection);
}
"""

    def test_lambda_is_summarized_from_comment_free_text(self):
        site = rc.harvest_callsites(self.SRC, "app/b.cpp")[0]
        self.assertEqual(
            site["snippet"],
            "QMetaObject::invokeMethod(self, [self, copy]() { calls: "
            "m_inFlightFrames.fetch_sub, copy.ok, handleFrameInternal }, "
            "Qt::QueuedConnection);")
        self.assertNotIn("explanatory comment", site["snippet"])
        self.assertEqual(site["connection"], "Qt::QueuedConnection")
        self.assertEqual(site["line"], 3)

    def test_long_call_keeps_connection_within_limit(self):
        args = ", ".join(f"argument_number_{i}" for i in range(40))
        src = f"connect({args}, Qt::BlockingQueuedConnection);"
        site = rc.harvest_callsites(src, "a.cpp")[0]
        self.assertLessEqual(len(site["snippet"]), rc.SNIPPET_LIMIT)
        self.assertTrue(site["snippet"].endswith("Qt::BlockingQueuedConnection);"))

    def test_old_index_snippet_is_clipped_without_losing_connection(self):
        old = {"file": "app/b.cpp", "line": 9, "doc": None,
               "snippet": "QMetaObject::invokeMethod(self, [self]() { // "
                          + "commentary " * 60 + "}, Qt::QueuedConnection);"}
        line = rc._callsite_line(old)
        self.assertIn("Qt::QueuedConnection", line)
        self.assertLessEqual(len(line), rc.SNIPPET_LIMIT + len("[app/b.cpp:9] "))


class TypeAndPurposeRendering(unittest.TestCase):
    TYPE = {"name": "qttune_frame_t", "kind": "struct",
            "members": ["timestamp_us", "data", "data_length"],
            "decl": "typedef struct qttune_frame {\n"
                    "    uint64_t timestamp_us; /* usec */\n"
                    "    uint8_t data[64];      /* Max CAN-FD payload */\n"
                    "    uint8_t data_length;\n} qttune_frame_t;",
            "doc": "Frame structure - POD only",
            "def_file": "core/include/qttune/core.h"}

    def test_type_shows_declaration_and_doc_without_comments(self):
        line = rc._type_line(self.TYPE)
        self.assertIn("uint8_t data[64];", line)
        self.assertIn("// Frame structure - POD only", line)
        self.assertNotIn("usec", line)
        self.assertNotIn("Max CAN-FD payload", line)

    def test_long_enum_is_cut_at_a_member_boundary(self):
        values = ", ".join(f"QT_STATUS_VALUE_{i} = {i}" for i in range(60))
        enum = {"name": "big_t", "kind": "enum", "members": [],
                "decl": f"typedef enum {{ {values} }} big_t;", "doc": None}
        line = rc._type_line(enum)
        body = line.split(": ", 1)[1]
        self.assertTrue(body.endswith(", …"), body[-30:])
        self.assertLessEqual(len(body), rc.TYPE_DECL_LIMIT + 2)

    def test_type_without_decl_falls_back_to_all_members(self):
        line = rc._type_line({k: v for k, v in self.TYPE.items() if k != "decl"})
        self.assertIn("timestamp_us, data, data_length", line)

    def test_purpose_cut_mid_word_is_clipped_at_a_word_boundary(self):
        purpose = ("Implements frame marshalling " * 10)[:200]
        self.assertTrue(purpose.endswith("marshalli"))  # cut mid-word, as stored
        clipped = rc._clip(purpose, rc.PURPOSE_LIMIT)
        self.assertTrue(clipped.endswith("frame…"), clipped[-20:])

    def test_complete_sentence_is_left_alone(self):
        self.assertEqual(rc._clip("A short purpose.", rc.PURPOSE_LIMIT),
                         "A short purpose.")

    def test_meta_files_collapse_into_one_line(self):
        index = dict(BuildContextPack.INDEX, files=BuildContextPack.INDEX["files"] + [
            {"path": "app/CMakeLists.txt", "purpose": "Build configuration",
             "layer": "meta"}])
        diff = "+++ b/app/CMakeLists.txt\n" + BuildContextPack.DIFF
        text, _ = rc.build_context_pack(diff, index)
        self.assertIn("Also modified (build/docs/CI, no summary): app/CMakeLists.txt",
                      text)
        self.assertNotIn("Build configuration", text)


if __name__ == "__main__":
    unittest.main()
    