"""Deterministic tests for retrieval (build_context_pack) and the
indexer's queued-connection call-site harvester. No network, no Ollama."""

import json
import unittest

import debate
import indexer
import retrieval as rc


class HarvestCallsites(unittest.TestCase):
    def test_detects_queued_connect(self):
        src = """
void Worker::setup() {
    // hand off to GUI thread
    connect(this, &Worker::frameReady,
            this, &Worker::onFrameReady, Qt::QueuedConnection);
}
"""
        sites = indexer.harvest_callsites(src, "app/worker.cpp")
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0]["file"], "app/worker.cpp")
        self.assertIn("Qt::QueuedConnection", sites[0]["snippet"])
        self.assertEqual(sites[0]["line"], 4)
        self.assertEqual(sites[0]["doc"], "hand off to GUI thread")

    def test_blocking_variant_detected(self):
        src = "invokeMethod(obj, SLOT(run()), Qt::BlockingQueuedConnection);"
        self.assertEqual(len(indexer.harvest_callsites(src, "a.cpp")), 1)

    def test_direct_connection_ignored(self):
        src = "connect(a, SIGNAL(x()), b, SLOT(y()));"
        self.assertEqual(len(indexer.harvest_callsites(src, "a.cpp")), 0)

    def test_commented_out_call_ignored(self):
        src = "// connect(this, s1, this, s2, Qt::QueuedConnection);\nint x;"
        self.assertEqual(len(indexer.harvest_callsites(src, "a.cpp")), 0)

    def test_long_multiline_lambda_connect(self):
        body = "\n".join(f"        auto tmp{i} = compute_something({i});"
                         for i in range(30))
        src = (f"connect(this, &Worker::frameReady, this,\n"
               f"        [this](const qttune_frame_t& f) {{\n{body}\n"
               f"        }}, Qt::QueuedConnection);\nint x;")
        sites = indexer.harvest_callsites(src, "app/worker.cpp")
        self.assertEqual(len(sites), 1)
        # Check the snippet starts with connect AND contains QueuedConnection
        self.assertIn("connect(this, &Worker::frameReady", sites[0]["snippet"])
        self.assertIn("Qt::QueuedConnection", sites[0]["snippet"])
        # The lambda is summarized, so the whole call fits, semicolon included
        self.assertTrue(sites[0]["snippet"].endswith("}, Qt::QueuedConnection);"))
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
        self.assertEqual(len(text), 50)  # the marker counts against the budget
        self.assertEqual(report["used"], 50)
        self.assertIn("truncated", text.lower())

    def test_report_counts_what_the_model_sees(self):
        # Code review 2026-10-23: the report counted every match, so a
        # capped or truncated pack read as if it showed them all.
        index = dict(self.INDEX, types=[
            {"name": f"type_{i}_t", "kind": "struct", "members": [],
             "def_file": "core/t.h"} for i in range(rc.MAX_TYPES + 5)])
        diff = self.DIFF + "\n+" + " ".join(t["name"] for t in index["types"])
        text, report = rc.build_context_pack(diff, index)
        self.assertEqual(report["sections"]["types"], rc.MAX_TYPES + 5)
        self.assertEqual(report["shown"]["types"], rc.MAX_TYPES)
        self.assertEqual(report["shown"]["types"], text.count("(struct):"))
        self.assertFalse(report["truncated"])
        cut = text.index("type_3_t (struct)")  # the budget ends inside the 4th type
        text, report = rc.build_context_pack(diff, index, budget=cut + 30)
        self.assertTrue(report["truncated"])
        self.assertEqual(report["shown"]["types"], 3)
        self.assertEqual(report["shown"]["call_sites"], 0)
        self.assertEqual(report["shown"]["modified_files"], 1)

    def test_missing_index_fails_visible_not_fatal(self):
        text, report = rc.build_context_pack(self.DIFF, {})
        self.assertEqual(text, "")
        self.assertIsNotNone(report["error"])

    def test_empty_diff_gives_empty_sections(self):
        text, report = rc.build_context_pack("", self.INDEX)
        self.assertIsNone(report["error"])
        self.assertEqual(report["sections"]["modified_files"], 0)

    def test_no_matches_gives_no_pack(self):
        # A bare pack header with no facts under it is noise.
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
        site = indexer.harvest_callsites(self.SRC, "app/b.cpp")[0]
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
        site = indexer.harvest_callsites(src, "a.cpp")[0]
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
        clipped = rc.clip(purpose, rc.PURPOSE_LIMIT)
        self.assertTrue(clipped.endswith("frame…"), clipped[-20:])

    def test_complete_sentence_is_left_alone(self):
        self.assertEqual(rc.clip("A short purpose.", rc.PURPOSE_LIMIT),
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


# ============ code review 2026-10-21, finding 6: pack accounting and sections ============

class PackAccountingAndSections(unittest.TestCase):
    INDEX = BuildContextPack.INDEX
    DIFF = BuildContextPack.DIFF

    def test_used_is_the_length_the_model_sees(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX)
        self.assertTrue(text)
        self.assertEqual(report["used"], len(text))

    def test_truncation_is_decided_on_the_real_length(self):
        # A budget between the old per-section undercount and the real
        # length used to slip through untruncated.
        full, _ = rc.build_context_pack(self.DIFF, self.INDEX)
        text, report = rc.build_context_pack(self.DIFF, self.INDEX,
                                             budget=len(full) - 1)
        self.assertIn("[... context truncated ...]", text)
        self.assertEqual(report["used"], len(full) - 1)

    def test_types_without_constants_have_no_empty_constants_header(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX)
        self.assertEqual(report["sections"]["constants"], 0)
        self.assertIn("--- KNOWN TYPES ---", text)
        self.assertNotIn("CONSTANTS", text)

    def test_constants_without_types_have_no_empty_types_header(self):
        text, _ = rc.build_context_pack(
            "+++ b/core/src/codec.c\n+if (n > MAX_FRAMES) return;", self.INDEX)
        self.assertIn("--- CONSTANTS ---\nMAX_FRAMES = 512", text)
        self.assertNotIn("KNOWN TYPES", text)

    def test_related_call_sites_do_not_need_a_direct_call_site(self):
        index = dict(self.INDEX, callsites=[
            {"file": "core/include/qttune.h", "line": 3, "doc": None,
             "snippet": "connect(a, s1, b, s2, Qt::QueuedConnection);"}])
        # codec.c has no call sites of its own; the type it uses does.
        text, report = rc.build_context_pack(
            "+++ b/core/src/codec.c\n+qttune_frame_t f;", index)
        self.assertNotIn("QUEUED CONNECTION CALL SITES", text)
        self.assertIn("--- RELATED CALL SITES (TYPE DEFINITIONS) ---\n"
                      "[core/include/qttune.h:3]", text)
        self.assertEqual(report["sections"]["related_call_sites"], 1)
        self.assertEqual(report["entries"], 3)  # file, type, related site

    def test_report_names_index_and_format_versions(self):
        index = dict(self.INDEX, index_version="idx_test")
        _, report = rc.build_context_pack(self.DIFF, index)
        self.assertEqual(report["index_version"], "idx_test")
        self.assertEqual(report["format_version"], rc.PACK_FORMAT_VERSION)

    def test_index_without_types_or_constants_still_retrieves(self):
        index = {"files": self.INDEX["files"]}
        text, report = rc.build_context_pack(self.DIFF, index)
        self.assertIn("Bridge between C core and QML UI", text)
        self.assertIsNone(report["error"])


# ============ code review 2026-10-21, finding 1: the diff wins ============

class DiffAuthoritativePack(unittest.TestCase):
    # Shaped like the bridge fixture: the diff deletes a class, a constant
    # and an in-flight counter that the indexed (pre-change) tree still has.
    INDEX = {
        "index_version": "idx_test",
        "source_commit": "e0c4c31" + "0" * 33,
        "files": [
            {"path": "app/qttunebridge.h", "layer": "bridge",
             "purpose": "Defines QtTuneBridge and SignalListModel for the QML UI."},
            {"path": "app/qttunebridge.cpp", "layer": "bridge",
             "purpose": "Implements QtTuneBridge frame handling."},
        ],
        "types": [],
        "constants": [
            {"name": "MaxInFlightFrames", "value": "1000", "kind": "const",
             "file": "app/qttunebridge.h"},
            {"name": "MaxFrames", "value": "10000", "kind": "const",
             "file": "app/qttunebridge.h"},
            {"name": "MAX_RETRIES", "value": "3", "kind": "define",
             "file": "core/include/limits.h"},
        ],
        "callsites": [
            {"file": "app/qttunebridge.cpp", "line": 390, "doc": None,
             "snippet": "QMetaObject::invokeMethod(self, [self, copy]() { calls: "
                        "m_inFlightFrames.fetch_sub, handleFrameInternal }, "
                        "Qt::QueuedConnection);"},
            {"file": "app/qttunebridge.cpp", "line": 370, "doc": None,
             "snippet": "QMetaObject::invokeMethod(self, [self]() { calls: "
                        "flushPending }, Qt::QueuedConnection);"},
        ],
    }
    DIFF = """diff --git a/app/qttunebridge.h b/app/qttunebridge.h
--- a/app/qttunebridge.h
+++ b/app/qttunebridge.h
@@ -10,9 +10,4 @@ class QtTuneBridge : public QObject
-class SignalListModel : public QAbstractListModel {};
-    static constexpr int MaxInFlightFrames = 1000;
-    std::atomic<int> m_inFlightFrames{0};
     static constexpr int MaxFrames = 10000;
+    int m_currentFrameCount = 0;
diff --git a/app/qttunebridge.cpp b/app/qttunebridge.cpp
--- a/app/qttunebridge.cpp
+++ b/app/qttunebridge.cpp
@@ -380,6 +380,4 @@ void QtTuneBridge::onFrame(const qttune_frame_t* f)
-    if (m_inFlightFrames.load() >= MaxInFlightFrames) return;
-    if (retries > MAX_RETRIES) return;
+    if (m_currentFrameCount >= MaxFrames) return;"""

    def pack(self):
        return rc.build_context_pack(self.DIFF, self.INDEX)

    def test_removed_identifiers_ignore_context_and_hunk_headers(self):
        removed = rc.removed_identifiers(self.DIFF)
        self.assertTrue({"SignalListModel", "MaxInFlightFrames",
                         "m_inFlightFrames", "MAX_RETRIES"} <= removed)
        # on a context line, an added line or a hunk header: still alive
        self.assertNotIn("MaxFrames", removed)
        self.assertNotIn("QtTuneBridge", removed)
        self.assertNotIn("onFrame", removed)

    def test_constant_the_diff_removes_is_omitted_and_named(self):
        text, report = self.pack()
        self.assertNotIn("MaxInFlightFrames = 1000", text)
        self.assertIn("MaxFrames = 10000", text)
        self.assertIn("--- OMITTED (indexed entries this diff removes or "
                      "rewrites) ---", text)
        self.assertIn("MaxInFlightFrames (constant, app/qttunebridge.h)", text)
        self.assertEqual(report["sections"]["constants"], 2)
        self.assertEqual(report["sections"]["omitted"], 2)

    def test_constant_outside_the_modified_files_is_kept(self):
        # Only removed lines use MAX_RETRIES, but its definition is in a
        # file the diff does not touch, so it still exists.
        text, _ = self.pack()
        self.assertIn("MAX_RETRIES = 3 (define)", text)

    def test_call_site_using_a_removed_member_is_omitted(self):
        text, report = self.pack()
        self.assertNotIn("[app/qttunebridge.cpp:390]", text)
        self.assertIn("[app/qttunebridge.cpp:370]", text)
        self.assertIn("queued call site in app/qttunebridge.cpp using "
                      "m_inFlightFrames", text)
        self.assertEqual(report["sections"]["call_sites"], 1)

    def test_purpose_naming_a_removed_class_says_so(self):
        text, _ = self.pack()
        self.assertIn("SignalListModel for the QML UI.  [only on the diff's "
                      "removed lines: SignalListModel]", text)
        self.assertNotIn("removed lines: QtTuneBridge", text)

    def test_nothing_claims_ground_truth_and_the_diff_wins(self):
        text, report = self.pack()
        wording = (text + debate.REPO_CONTEXT_TEMPLATE).lower()
        self.assertNotIn("ground truth", wording)
        self.assertIn("the code diff is authoritative", wording)
        self.assertIn("machine-written", wording)
        self.assertEqual(report["index_commit"], self.INDEX["source_commit"])


def json_copy(obj):
    return json.loads(json.dumps(obj))


class HarvestDefinitions(unittest.TestCase):
    """Data members and the functions that assign them (pack f4; ADR-0002,
    twentieth measurement)."""

    SRC = """
struct transport {
    /* resolved channels */
    channel chans[MAX_CHANNELS] = {};
    uint32_t chan_count = 0;
    std::atomic<bool> stop{false};
};

class Bridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
public:
    int rowCount(const QModelIndex& parent = {}) const override;
    int count() const { return m_count; }
private:
    int m_count = 0, m_other = 1;
    QTimer* m_timer = nullptr;
};

void resolve(transport* t, int n)
{
    if (n > 0) {
        t->chans[0].rx_id = 7;
    } else if (n < 0) {
        return;
    }
    t->chan_count = n;
}

void Bridge::reset()
{
    int local = 0;
    m_count = 0;
    ++m_other;
    if (m_count == local) {}
}

void Bridge::stop(transport* t)
{
    t->stop.store(true);
}
"""

    def setUp(self):
        self.members, self.functions = indexer.harvest_definitions(self.SRC)
        self.by_name = {f["name"]: f for f in self.functions}

    def test_members_of_structs_and_classes(self):
        got = {(m["owner"], m["name"]) for m in self.members}
        self.assertEqual(got, {("transport", "chans"), ("transport", "chan_count"),
                               ("transport", "stop"), ("Bridge", "m_count"),
                               ("Bridge", "m_other"), ("Bridge", "m_timer")})
        chans = next(m for m in self.members if m["name"] == "chans")
        self.assertEqual(chans["decl"], "channel chans[MAX_CHANNELS] = {};")
        self.assertEqual(chans["line"], 4)

    def test_a_default_argument_brace_is_not_a_body(self):
        # 'rowCount(... = {}) const override;' once yielded a member
        # named 'override' and a function rowCount (Step 0)
        self.assertNotIn("override", {m["name"] for m in self.members})
        self.assertNotIn("rowCount", self.by_name)

    def test_functions_with_owner_and_span(self):
        self.assertIsNone(self.by_name["resolve"]["owner"])
        self.assertEqual(self.by_name["Bridge::reset"]["owner"], "Bridge")
        self.assertEqual(self.by_name["count"]["owner"], "Bridge")  # inline method
        self.assertEqual((self.by_name["resolve"]["line"],
                          self.by_name["resolve"]["end_line"]), (20, 28))
        self.assertNotIn("if", self.by_name)

    def test_writes_by_form(self):
        w = self.by_name["resolve"]["writes"]
        self.assertEqual(w["chans"], ["pointer"])   # through a chain
        self.assertEqual(w["rx_id"], ["object"])
        self.assertEqual(w["chan_count"], ["pointer"])
        reset = self.by_name["Bridge::reset"]["writes"]
        self.assertEqual(reset["m_count"], ["bare"])
        self.assertEqual(reset["m_other"], ["bare"])  # prefix ++
        self.assertEqual(self.by_name["Bridge::stop"]["writes"]["stop"], ["atomic"])

    def test_comparisons_are_not_writes(self):
        self.assertNotIn("n", self.by_name["resolve"]["writes"])  # n > 0, n < 0

    def test_function_lines_are_comment_free_and_dedented(self):
        lines = self.by_name["resolve"]["lines"]
        self.assertEqual(lines[0], "void resolve(transport* t, int n)")
        self.assertEqual(lines[-1], "}")
        self.assertIn("  t->chan_count = n;", lines)


class FieldSection(unittest.TestCase):
    """The FIELD DEFINITIONS AND WRITERS pack section."""

    INDEX = {
        "files": [{"path": "core/t.cpp", "purpose": "transport", "layer": "core"}],
        "types": [], "constants": [], "callsites": [],
        "fields": [
            {"owner": "transport", "name": "chans", "file": "core/t.cpp",
             "line": 4, "decl": "channel chans[MAX] = {};"},
            {"owner": "transport", "name": "chan_count", "file": "core/t.cpp",
             "line": 5, "decl": "uint32_t chan_count = 0;"},
        ],
        "functions": [
            {"name": "resolve", "owner": None, "file": "core/t.cpp", "line": 20,
             "end_line": 24, "writes": {"chans": ["pointer"], "chan_count": ["pointer"]},
             "lines": ["void resolve(transport* t)", "{", " t->chan_count = 1;", "}"]},
            {"name": "worker", "owner": None, "file": "core/t.cpp", "line": 40,
             "end_line": 60, "writes": {"chan_count": ["pointer"]},
             "lines": ["void worker(transport* t)", "{", " t->chan_count = 0;", "}"]},
        ],
    }
    DIFF = (
        "--- a/core/t.cpp\n+++ b/core/t.cpp\n"
        "@@ -45,3 +45,3 @@ void worker(transport* t)\n"
        "     int x = 0;\n"
        "-    send(t->chans[ci].tx_id);\n"
        "+    send(t->chans[0].tx_id);\n"
        "     if (t->chan_count == 0) return;\n")

    def test_declarations_and_unchanged_writers_are_shown(self):
        text, report = rc.build_context_pack(self.DIFF, self.INDEX)
        self.assertIn("--- FIELD DEFINITIONS AND WRITERS", text)
        self.assertIn("transport::chans [core/t.cpp:4] channel chans[MAX] = {};", text)
        self.assertIn("writes chan_count, chans  [core/t.cpp:20-24]", text)
        self.assertIn(" t->chan_count = 1;", text)
        self.assertEqual(report["sections"]["fields"], 3)

    def test_a_function_the_diff_changes_is_left_out(self):
        _, report = rc.build_context_pack(self.DIFF, self.INDEX)
        rows = {w["function"]: w["dropped"] for w in report["field_audit"]["writers"]}
        self.assertEqual(rows, {"resolve": None, "worker": "changed by the diff"})

    def test_a_declaration_inside_a_hunk_is_left_out(self):
        diff = self.DIFF.replace("@@ -45,3 +45,3 @@", "@@ -3,3 +3,3 @@")
        _, report = rc.build_context_pack(diff, self.INDEX)
        dropped = {d["name"]: d["dropped"] for d in report["field_audit"]["decls"]}
        self.assertEqual(dropped["chans"], "in a hunk")

    def test_calls_are_not_member_uses(self):
        diff = self.DIFF.replace("t->chan_count == 0", "t->chan_count() == 0")
        _, report = rc.build_context_pack(diff, self.INDEX)
        self.assertNotIn("chan_count", report["field_audit"]["uses"])

    def test_a_writer_naming_removed_project_code_is_omitted(self):
        index = json_copy(self.INDEX)
        index["functions"][0]["lines"].insert(2, " helper_ci(t);")
        index["functions"].append({"name": "helper_ci", "owner": None,
                                   "file": "core/x.cpp", "line": 1, "end_line": 2,
                                   "writes": {}, "lines": []})
        diff = self.DIFF.replace("send(t->chans[ci].tx_id);",
                                 "send(t->chans[helper_ci(t)].tx_id);")
        text, report = rc.build_context_pack(diff, index)
        rows = {w["function"]: w["dropped"] for w in report["field_audit"]["writers"]}
        self.assertEqual(rows["resolve"], "names removed code: helper_ci")
        self.assertIn("writer resolve (core/t.cpp) using helper_ci", text)

    def test_removed_keywords_do_not_omit_a_writer(self):
        # 'static_cast' on a removed line is not project code (Step 0)
        index = json_copy(self.INDEX)
        index["functions"][0]["lines"].insert(2, " int n = static_cast<int>(1);")
        diff = self.DIFF.replace("send(t->chans[ci].tx_id);",
                                 "send(static_cast<int>(t->chans[ci].tx_id));")
        _, report = rc.build_context_pack(diff, index)
        rows = {w["function"]: w["dropped"] for w in report["field_audit"]["writers"]}
        self.assertIsNone(rows["resolve"])

    def test_long_writer_keeps_head_and_tail(self):
        index = json_copy(self.INDEX)
        index["functions"][0]["lines"] = (["void resolve(transport* t)", "{"]
                                          + [f" step{i}();" for i in range(40)]
                                          + [" t->chan_count = n;", "}"])
        text, report = rc.build_context_pack(self.DIFF, index)
        self.assertIn(" t->chan_count = n;", text)
        self.assertIn("\n…\n", text)
        self.assertNotIn("step20();", text)
        row = report["field_audit"]["writers"][0]
        self.assertEqual((row["shown_lines"], row["lines"]),
                         (rc.WRITER_LINES - 1, 44))

    def test_index_without_fields_has_no_section(self):
        index = {k: v for k, v in self.INDEX.items() if k not in ("fields", "functions")}
        text, report = rc.build_context_pack(self.DIFF, index)
        self.assertNotIn("FIELD DEFINITIONS", text)
        self.assertEqual(report["sections"]["fields"], 0)


if __name__ == "__main__":
    unittest.main()
    