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


if __name__ == "__main__":
    unittest.main()
    