#!/usr/bin/env python3
"""
Generic Test Environment Engine
================================
Auto-discovers tests from SV files and the TB, generates a custom TB
with only the user-selected tests, compiles via VCS, runs, parses pass/fail.
No hard-coded test names or categories — everything is read from the files.
Python 3.6 compatible.
"""

import subprocess
import os
import re
import glob
import random
import datetime

# =============================================================================
# CONFIGURATION — edit these paths for your project
# =============================================================================

PROJECT_DIR  = "/users/epstmh/Project_B/rev12"
TB_FILE      = os.path.join(PROJECT_DIR, "RTL", "top_iris_tb.sv")
TESTS_DIR    = os.path.join(PROJECT_DIR, "functions", "tests_separate")
FILELIST_SRC = os.path.join(PROJECT_DIR, "filelist")
LOG_DIR      = os.path.join(PROJECT_DIR, "python_runner_with_params", "logs")
GEN_DIR      = os.path.join(PROJECT_DIR, "python_runner_with_params", "generated")
GEN_TB       = os.path.join(GEN_DIR, "generated_tb.sv")
GEN_FILELIST = os.path.join(GEN_DIR, "filelist_generated")

VCS_BASE_CMD = [
    "vcs", "-kdb", "-sverilog", "-v2k_generate",
    "-debug_access+all", "-full64",
    "-ignore", "initializer_driver_checks",
    "+define+ARM_DISABLE_EMA_CHECK",
    "+define+VALIDATION",
    "+incdir+/users/shukir/logic_design/Project/design/work/include",
]

ENDLESS_LOOP_LIMIT = 100
FINISH_PATTERN = re.compile(r"\$finish\s*;")
CATEGORY_COMMENT_RE = re.compile(r"//\*+\s*(.*?)\s*\*+//")

SETUP_TASKS = frozenset([
    "setup_memory_mode", "setup_to_1adc", "setup_to_4adcs",
    "setup_for_general_startup", "setup_for_flops_memory",
    "setup_to_memory_on_flops_function", "setup_to_memory_function",
    "clean_up_buffers",
])

# =============================================================================
# PER-TEST PARAMETER SPECS
# =============================================================================
# Each entry declares that a test's SV task takes one or more arguments and how
# Python should resolve them (manual value provided by the user, or randomized
# within [min, max]). The generated TB will call the task with the resolved
# values, e.g. hw_write_one_full_buffer(1234);
#
# Only tests listed here get parameterized calls; all others keep their
# existing SV call as discovered from the testbench.
#
# Param fields:
#   name   : parameter name (matches the SV task argument name conceptually)
#   type   : "int" | "logic"       (only used for display / GUI)
#   width  : e.g. "[10:0]"         (only used for display)
#   min    : int, OR the name (string) of a previously listed param whose
#            resolved value is used as the effective min
#   max    : int, OR the name (string) of a previously listed param
#
# Params are resolved in list order, so later params can reference earlier
# ones by name (e.g. x's min = partial_address).
TEST_PARAM_SPECS = {
    12: {
        "task_name": "hw_write_one_full_buffer",
        "params": [
            {"name": "number_of_cycles", "type": "int", "min": 0, "max": 5000},
        ],
    },
    13: {
        "task_name": "hw_write_one_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 2048},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 5000},
            {"name": "param",            "type": "int", "min": 100,               "max": 5000},
        ],
    },
    14: {
        "task_name": "hw_write_endless_full_buffer",
        "params": [
            {"name": "param", "type": "int", "min": 100, "max": 5000},
        ],
    },
    15: {
        "task_name": "hw_write_endless_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 2048},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 5000},
            {"name": "param",            "type": "int", "min": 100,               "max": 5000},
        ],
    },
    18: {
        "task_name": "hw_write_one_full_buffer",
        "params": [
            {"name": "number_of_cycles", "type": "int", "min": 0, "max": 5000},
        ],
    },
    19: {
        "task_name": "hw_write_one_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[6:0]",
             "min": 10, "max": 128},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 2000},
            {"name": "param",            "type": "int", "min": 100,               "max": 3000},
        ],
    },
    20: {
        "task_name": "hw_write_endless_full_buffer",
        "params": [
            {"name": "param", "type": "int", "min": 100, "max": 3000},
        ],
    },
    21: {
        "task_name": "hw_write_endless_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 128},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 2000},
            {"name": "param",            "type": "int", "min": 100,               "max": 3000},
        ],
    },
    22: {
        "task_name": "hw_write_ds_one_full_buffer",
        "params": [
            {"name": "number_of_cycles", "type": "int",   "min": 0, "max": 5000},
            {"name": "ds_number",        "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
    23: {
        "task_name": "hw_write_ds_one_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 2048},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 5000},
            {"name": "param",            "type": "int", "min": 100,               "max": 5000},
            {"name": "ds_number",        "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
    24: {
        "task_name": "hw_write_ds_endless_full_buffer",
        "params": [
            {"name": "param", "type": "int", "min": 100, "max": 5000},
        ],
    },
    25: {
        "task_name": "hw_write_ds_endless_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 2048},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 5000},
            {"name": "param",            "type": "int", "min": 100,               "max": 5000},
            {"name": "ds_number",        "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
    26: {
        "task_name": "hw_write_ds_one_full_buffer",
        "params": [
            {"name": "number_of_cycles", "type": "int", "min": 0, "max": 5000},
        ],
    },
    27: {
        "task_name": "hw_write_ds_one_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[6:0]",
             "min": 10, "max": 128},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 2000},
            {"name": "param",            "type": "int", "min": 100,               "max": 3000},
            {"name": "ds_number",        "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
    28: {
        "task_name": "hw_write_ds_endless_full_buffer",
        "params": [
            {"name": "param",     "type": "int",   "min": 100, "max": 3000},
            {"name": "ds_number", "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
    29: {
        "task_name": "hw_write_ds_endless_partial_buffer",
        "params": [
            {"name": "partial_address",  "type": "logic", "width": "[10:0]",
             "min": 10, "max": 128},
            {"name": "number_of_cycles", "type": "int", "min": "partial_address", "max": 2000},
            {"name": "param",            "type": "int", "min": 100,               "max": 3000},
            {"name": "ds_number",        "type": "logic", "width": "[11:0]",
             "min": 8, "max": 4096},
        ],
    },
}


def get_test_param_spec(test_id):
    return TEST_PARAM_SPECS.get(test_id)


def _resolve_bound(bound, resolved, test_id, param_name, which):
    """Resolve a min/max value which may be a literal int or the name of an
    earlier param (whose resolved int value is used instead).
    """
    if isinstance(bound, int):
        return bound
    if isinstance(bound, str):
        if bound in resolved:
            return resolved[bound]
        raise ValueError(
            "Test {}: param '{}' {} references unknown/unresolved param '{}'".format(
                test_id, param_name, which, bound))
    raise ValueError(
        "Test {}: param '{}' has invalid {} ({!r})".format(
            test_id, param_name, which, bound))


def format_param_range_text(p):
    """Human-readable range text like '[10..2048]' or '[partial_address..5000]'."""
    lo = p["min"] if isinstance(p["min"], int) else str(p["min"])
    hi = p["max"] if isinstance(p["max"], int) else str(p["max"])
    return "[{}..{}]".format(lo, hi)


def resolve_test_params(test_id, overrides=None):
    """Resolve parameters for a single test.

    overrides: dict like {param_name: {"mode": "manual"|"random", "value": int}}
               If a param is missing, defaults to random within [min, max].

               For mode=="random" the caller MAY pre-resolve the value (e.g.
               the GUI/CLI rolls the random value up-front so the user can see
               it, and so dependent-parameter validation can be done live).
               When a pre-resolved value is given and it falls inside the
               effective [min, max], it is honored as-is. Otherwise a fresh
               random value is drawn here.

    Params are resolved in order, so later params may reference earlier
    resolved values via a string min/max (e.g. number_of_cycles's min =
    "partial_address").

    Returns: dict {param_name: concrete_int_value}, or None if no spec exists.
    Raises ValueError on bad manual input (not an int, out of range, missing).
    """
    spec = get_test_param_spec(test_id)
    if not spec:
        return None
    overrides = overrides or {}
    resolved = {}
    for p in spec["params"]:
        name = p["name"]
        ov = overrides.get(name, {}) or {}
        mode = (ov.get("mode") or "random").lower()

        eff_min = _resolve_bound(p["min"], resolved, test_id, name, "min")
        eff_max = _resolve_bound(p["max"], resolved, test_id, name, "max")
        if eff_min > eff_max:
            raise ValueError(
                "Test {}: param '{}' has empty range [{}, {}]".format(
                    test_id, name, eff_min, eff_max))

        if mode == "manual":
            raw = ov.get("value")
            if raw is None or raw == "":
                raise ValueError(
                    "Test {}: manual value required for param '{}'".format(test_id, name))
            try:
                val = int(raw)
            except (TypeError, ValueError):
                raise ValueError(
                    "Test {}: param '{}' must be an integer (got {!r})".format(test_id, name, raw))
            if val < eff_min or val > eff_max:
                raise ValueError(
                    "Test {}: param '{}'={} out of range [{}, {}]".format(
                        test_id, name, val, eff_min, eff_max))
        else:
            raw = ov.get("value")
            val = None
            if raw is not None and raw != "":
                try:
                    cand = int(raw)
                    if eff_min <= cand <= eff_max:
                        val = cand
                except (TypeError, ValueError):
                    val = None
            if val is None:
                val = random.randint(eff_min, eff_max)

        resolved[name] = val
    return resolved


def format_sv_call_from_spec(test_id, resolved_params):
    """Render the SV task call line from a spec + resolved params."""
    spec = get_test_param_spec(test_id)
    if not spec:
        return None
    args = ", ".join(str(resolved_params[p["name"]]) for p in spec["params"])
    return "{}({});".format(spec["task_name"], args)

# =============================================================================
# AUTO-DISCOVERY — reads tests_separate/*.sv and the TB
# =============================================================================

def discover_tests_from_files(tests_dir):
    """Scan test_*.sv files in tests_dir.
    Returns a list of dicts, each with keys:
      id, alt_id, task_name, description, call_signature, filename
    """
    tests = []
    pattern = os.path.join(tests_dir, "test_*.sv")
    for filepath in sorted(glob.glob(pattern)):
        fname = os.path.basename(filepath)
        if fname == "tests_include.sv":
            continue

        with open(filepath, "r") as f:
            content = f.read()
            lines = content.splitlines()

        # Parse test IDs from first comment line: "// Test No. 10/16 - description"
        test_ids = []
        description = fname
        for line in lines[:5]:
            m = re.search(r"Test No\.\s*([\d/]+)\s*-\s*(.*)", line)
            if m:
                id_str = m.group(1)
                description = m.group(2).strip()
                for part in id_str.split("/"):
                    part = part.strip()
                    if part.isdigit():
                        test_ids.append(int(part))
                break

        # If no "Test No." found, try to get IDs from filename: test_10_16_...
        if not test_ids:
            m = re.match(r"test_([\d_]+?)_[a-zA-Z]", fname)
            if m:
                for part in m.group(1).split("_"):
                    if part.isdigit():
                        test_ids.append(int(part))

        if not test_ids:
            continue

        # Parse task name and signature from "task <name>(...)"
        task_name = None
        call_signature = None
        for line in lines[:10]:
            tm = re.search(r"task\s+(\w+)\s*\(([^)]*)\)\s*;", line)
            if tm:
                task_name = tm.group(1)
                args_raw = tm.group(2).strip()
                if args_raw:
                    call_signature = "HAS_ARGS"
                else:
                    call_signature = "NO_ARGS"
                break

        if task_name is None:
            continue

        primary_id = test_ids[0]
        alt_id = test_ids[1] if len(test_ids) > 1 else None

        tests.append({
            "id": primary_id,
            "alt_id": alt_id,
            "task_name": task_name,
            "description": description,
            "call_signature": call_signature,
            "filename": fname,
        })

    return tests


def discover_tb_structure(tb_file):
    """Parse the TB to discover:
    1. How each task is called (the exact SV call line)
    2. Which section/category each call belongs to
    3. Memory mode and flops_tests_index context

    Scans from the start of the file to $finish — no reset marker needed.
    The existing filters (setup tasks, $-calls, etc.) skip non-test content.

    Returns a list of dicts:
      task_name, sv_call, category, memory_on_flops (None/False/True), flops_tests_index
    """
    with open(tb_file, "r") as f:
        tb_lines = f.readlines()

    entries = []
    current_category = "General"
    flops_tests_index = 0
    in_loop = False
    loop_depth = 0

    for line in tb_lines:
        stripped = line.strip()

        if FINISH_PATTERN.search(stripped):
            break

        m = CATEGORY_COMMENT_RE.match(stripped)
        if m:
            cat_text = m.group(1).strip()
            if cat_text:
                current_category = cat_text
            continue

        if re.search(r"for\s*\(int\s+i\s*=", stripped):
            in_loop = True
            continue

        if in_loop and stripped == "end":
            loop_depth -= 1
            if loop_depth < 0:
                in_loop = False
                loop_depth = 0
            continue
        if in_loop and "begin" in stripped and not stripped.startswith("//"):
            loop_depth += 1

        if re.search(r"memory_on_flops\s*=", stripped):
            continue
        if "setup_memory_mode" in stripped:
            continue

        m = re.search(r"flops_tests_index\s*=\s*(\d+)", stripped)
        if m:
            flops_tests_index = int(m.group(1))
            continue

        if stripped.startswith("//"):
            continue

        tm = re.match(r"(\w+)\s*\(([^)]*)\)\s*;", stripped)
        if tm:
            call_task = tm.group(1)
            if call_task.startswith("$") or call_task in SETUP_TASKS:
                continue

            sv_call = stripped
            if in_loop:
                entries.append({
                    "task_name": call_task, "sv_call": sv_call,
                    "category": current_category,
                    "memory_on_flops": False,
                    "flops_tests_index": flops_tests_index,
                })
                entries.append({
                    "task_name": call_task, "sv_call": sv_call,
                    "category": current_category,
                    "memory_on_flops": True,
                    "flops_tests_index": flops_tests_index,
                })
            else:
                entries.append({
                    "task_name": call_task, "sv_call": sv_call,
                    "category": current_category,
                    "memory_on_flops": None,
                    "flops_tests_index": None,
                })

    return entries


def build_test_db(tests_dir, tb_file):
    """Combine file discovery + TB parsing to build the full test database.
    Returns (test_list, categories_dict).

    test_list: list of dicts with id, task_name, description, category, sv_call,
               memory_on_flops, flops_tests_index, all_ids
    categories_dict: {category_name: [test_ids]}
    """
    file_tests = discover_tests_from_files(tests_dir)
    tb_entries = discover_tb_structure(tb_file)

    # Build a map: task_name -> list of TB entries (one per memory mode)
    tb_map = {}
    for e in tb_entries:
        tb_map.setdefault(e["task_name"], []).append(e)

    test_list = []
    seen_ids = set()

    for ft in file_tests:
        task_name = ft["task_name"]
        tb_calls = tb_map.get(task_name, [])

        if not tb_calls:
            # Task not called in TB — still add it as standalone
            if ft["id"] not in seen_ids:
                test_list.append({
                    "id": ft["id"],
                    "task_name": task_name,
                    "description": ft["description"],
                    "category": "Uncategorized",
                    "sv_call": "{}();".format(task_name) if ft["call_signature"] == "NO_ARGS" else None,
                    "memory_on_flops": None,
                    "flops_tests_index": None,
                    "all_ids": [ft["id"]] + ([ft["alt_id"]] if ft["alt_id"] else []),
                })
                seen_ids.add(ft["id"])
            continue

        for tb_e in tb_calls:
            # Determine which test ID this TB entry corresponds to
            if tb_e["memory_on_flops"] is None:
                # Standalone test
                tid = ft["id"]
            elif tb_e["memory_on_flops"] is False:
                tid = ft["id"]
            else:
                tid = ft["alt_id"] if ft["alt_id"] else ft["id"]

            if tid is None or tid in seen_ids:
                continue

            test_list.append({
                "id": tid,
                "task_name": task_name,
                "description": ft["description"],
                "category": tb_e["category"],
                "sv_call": tb_e["sv_call"],
                "memory_on_flops": tb_e["memory_on_flops"],
                "flops_tests_index": tb_e["flops_tests_index"],
                "all_ids": [ft["id"]] + ([ft["alt_id"]] if ft["alt_id"] else []),
            })
            seen_ids.add(tid)

    test_list.sort(key=lambda t: t["id"])

    categories = {}
    for t in test_list:
        categories.setdefault(t["category"], []).append(t["id"])

    return test_list, categories

# =============================================================================
# MODULE-LEVEL: auto-discover on import
# =============================================================================

TEST_LIST, CATEGORIES = build_test_db(TESTS_DIR, TB_FILE)

def get_test(identifier):
    for t in TEST_LIST:
        if t["id"] == identifier or t["task_name"] == identifier:
            return t
    return None

def get_all_tests():
    return list(TEST_LIST)

def get_tests_by_category(category):
    return [t for t in TEST_LIST if t["category"] == category]

def print_available_tests():
    """Print all discovered tests grouped by category."""
    print("\n" + "=" * 70)
    print("  AVAILABLE TESTS (auto-discovered)")
    print("=" * 70)
    cur_cat = None
    for t in TEST_LIST:
        if t["category"] != cur_cat:
            cur_cat = t["category"]
            print("\n  --- {} ---".format(cur_cat))
        print("    Test {}: {}  ({})".format(t["id"], t["task_name"], t["description"]))
    print("\n  CATEGORIES: {}".format(", ".join('"{}"'.format(c) for c in CATEGORIES)))
    print("=" * 70 + "\n")

# =============================================================================
# TB GENERATOR — reads real TB, replaces test section
# =============================================================================

def _build_test_calls(selected_tests, resolved_param_map=None):
    """Build the SV code for just the selected test calls.

    resolved_param_map: {test_id: {param_name: int_value}} for tests that have
    a TEST_PARAM_SPECS entry. When present, the emitted call is rebuilt from
    the spec instead of reusing the static sv_call discovered from the TB.
    """
    lines = []
    resolved_param_map = resolved_param_map or {}

    def _call_for(test_entry):
        tid = test_entry.get("id")
        if tid in resolved_param_map and get_test_param_spec(tid):
            return format_sv_call_from_spec(tid, resolved_param_map[tid])
        sv_call = test_entry.get("sv_call")
        if isinstance(sv_call, str) and sv_call.strip():
            return sv_call
        raise ValueError(
            "Missing SV call for test id={} task='{}'. "
            "This test likely needs arguments and is not mapped in the testbench call section.".format(
                test_entry.get("id"), test_entry.get("task_name")
            )
        )

    # Standalone tests (memory_on_flops is None)
    standalone = [t for t in selected_tests if t["memory_on_flops"] is None]
    if standalone:
        lines.append("")
        lines.append("\t//*****************************************************************//")
        lines.append("\t//*** Standalone Tests ********************************************//")
        lines.append("\t//*****************************************************************//")
        for t in standalone:
            lines.append("")
            lines.append("\t// Test No. {}".format(t["id"]))
            lines.append("\t" + _call_for(t))

    # Memory-mode tests: group by (memory_on_flops, flops_tests_index)
    mem_tests = [t for t in selected_tests if t["memory_on_flops"] is not None]
    if not mem_tests:
        lines.append("")
        return "\n".join(lines)

    need_memory = any(t["memory_on_flops"] is False for t in mem_tests)
    need_flops  = any(t["memory_on_flops"] is True  for t in mem_tests)

    for mode_val, sv_bool, label in [(False, "FALSE", "Memory"), (True, "TRUE", "Memory on Flops")]:
        if mode_val is False and not need_memory:
            continue
        if mode_val is True and not need_flops:
            continue

        mode_tests = [t for t in mem_tests if t["memory_on_flops"] == mode_val]
        if not mode_tests:
            continue

        lines.append("")
        lines.append("\t//*****************************************************************//")
        lines.append("\t//*** {} mode {}//".format(label, "*" * (53 - len(label))))
        lines.append("\t//*****************************************************************//")
        lines.append("\tmemory_on_flops = {};".format(sv_bool))
        lines.append('\t$display("*** Tests with {} ***");'.format(label))
        lines.append("\tsetup_memory_mode(memory_on_flops);")

        # Group by flops_tests_index, preserving order
        seen_fi = []
        fi_groups = {}
        for t in mode_tests:
            fi = t["flops_tests_index"]
            if fi not in fi_groups:
                seen_fi.append(fi)
                fi_groups[fi] = []
            fi_groups[fi].append(t)

        for fi in seen_fi:
            lines.append("")
            lines.append("\tflops_tests_index = {};".format(fi))
            for t in fi_groups[fi]:
                lines.append("")
                lines.append("\t// Test No. {}".format(t["id"]))
                lines.append("\t" + _call_for(t))

    lines.append("")
    return "\n".join(lines)


def _find_test_section_start(tb_lines):
    """Find the line index where test content begins in the TB.
    Looks for the first category comment (//*** ... ***// ) or
    the first known test task call — whichever comes first.
    Everything before that line is kept as the header (setup, reset, etc.).
    """
    all_test_names = set(t["task_name"] for t in TEST_LIST)
    for i, line in enumerate(tb_lines):
        stripped = line.strip()
        if CATEGORY_COMMENT_RE.match(stripped):
            return i
        tm = re.match(r"(\w+)\s*\(", stripped)
        if tm and tm.group(1) in all_test_names:
            return i
    return None


def generate_tb_and_filelist(selected_tests, param_overrides=None):
    """Read the TB, replace the test section with only selected tests.
    The TB's own setup (reset, clocks, etc.) is preserved untouched.

    param_overrides: {test_id: {param_name: {"mode": "manual"|"random", "value": int}}}
    Tests listed in TEST_PARAM_SPECS will have their SV call regenerated with
    the resolved values. Tests without a spec are unaffected.
    """
    os.makedirs(GEN_DIR, exist_ok=True)

    param_overrides = param_overrides or {}
    resolved_map = {}
    any_params = False
    for t in selected_tests:
        spec = get_test_param_spec(t["id"])
        if spec is None:
            continue
        if not any_params:
            print("\n[PARAMS] Resolved parameters for this run:")
            any_params = True
        t_over = param_overrides.get(t["id"]) or {}
        resolved = resolve_test_params(t["id"], t_over)
        resolved_map[t["id"]] = resolved
        print("  Test {:<3} {}".format(t["id"], spec["task_name"]))
        for p in spec["params"]:
            pname = p["name"]
            mode = ((t_over.get(pname) or {}).get("mode") or "random").lower()
            tag = "[MANUAL]" if mode == "manual" else "[RANDOM]"
            rng = format_param_range_text(p)
            print("    {} {:<16} = {:<8} {}".format(
                tag, pname, resolved[pname], rng))

    with open(TB_FILE, "r") as f:
        tb_lines = f.readlines()

    header_end = _find_test_section_start(tb_lines)
    if header_end is None:
        raise RuntimeError("Could not find any test calls or category comments in {}".format(TB_FILE))

    footer_start = None
    for i, line in enumerate(tb_lines):
        if FINISH_PATTERN.search(line):
            footer_start = i
            break
    if footer_start is None:
        raise RuntimeError("Could not find '$finish;' in {}".format(TB_FILE))

    header = "".join(tb_lines[:header_end])
    footer = "".join(tb_lines[footer_start:])

    test_section = _build_test_calls(selected_tests, resolved_param_map=resolved_map)

    with open(GEN_TB, "w") as f:
        f.write(header)
        f.write(test_section)
        f.write("\n")
        f.write(footer)

    tb_basename = os.path.splitext(os.path.basename(TB_FILE))[0]
    with open(FILELIST_SRC, "r") as f:
        fl_lines = f.readlines()

    with open(GEN_FILELIST, "w") as f:
        for line in fl_lines:
            if tb_basename in line:
                f.write(GEN_TB + "\n")
            else:
                f.write(line)

    print("[INFO] Generated TB      : {}".format(GEN_TB))
    print("[INFO] Generated filelist: {}".format(GEN_FILELIST))
    return GEN_TB, GEN_FILELIST, resolved_map


def format_params_inline(test_id, resolved_map, param_overrides=None):
    """Build a short, readable string for a test's resolved params.
    Returns "" for tests without a spec. Example:
        "partial_address=500[MANUAL], x=3120[RANDOM], param=2500[MANUAL]"
    """
    spec = get_test_param_spec(test_id)
    if not spec or not resolved_map or test_id not in resolved_map:
        return ""
    resolved = resolved_map[test_id] or {}
    ov = (param_overrides or {}).get(test_id) or {}
    parts = []
    for p in spec["params"]:
        name = p["name"]
        mode = ((ov.get(name) or {}).get("mode") or "random").lower()
        tag = "MANUAL" if mode == "manual" else "RANDOM"
        parts.append("{}={}[{}]".format(name, resolved.get(name), tag))
    return ", ".join(parts)

# =============================================================================
# COMPILE & RUN
# =============================================================================

def compile_and_run(filelist_path, verbose_stdout=True):
    os.makedirs(LOG_DIR, exist_ok=True)
    cmd = list(VCS_BASE_CMD) + ["-f", filelist_path]

    print("\n[INFO] Compiling...")
    print("[CMD] " + " ".join(cmd))

    try:
        comp = subprocess.run(cmd, cwd=PROJECT_DIR,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("[ERROR] Compilation timed out!"); return None
    except OSError as e:
        print("[ERROR] Cannot start VCS: {}".format(e)); return None

    if comp.returncode != 0:
        print("[ERROR] Compilation failed!")
        print(comp.stdout); print(comp.stderr); return None

    print("[INFO] Compilation OK. Running simulation...")
    simv = os.path.join(PROJECT_DIR, "simv")
    try:
        sim = subprocess.run([simv], cwd=PROJECT_DIR,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=3600)
    except subprocess.TimeoutExpired:
        print("[ERROR] Simulation timed out!"); return None
    except OSError as e:
        print("[ERROR] Cannot start simv: {}".format(e)); return None

    output = sim.stdout + sim.stderr
    if verbose_stdout:
        print("\n[SIMULATION OUTPUT]")
        print("-" * 60)
        print(output)
        print("-" * 60)
    return output

# =============================================================================
# LOG PARSER
# =============================================================================

def parse_results(output, selected_tests, resolved_map=None, param_overrides=None):
    results = {}
    for t in selected_tests:
        tid = t["id"]
        results[tid] = {"id": tid, "name": t["task_name"], "category": t["category"],
                        "description": t["description"], "status": "UNKNOWN", "errors": [],
                        "params_text": format_params_inline(tid, resolved_map, param_overrides)}

    for line in output.splitlines():
        m = re.search(r"Test\s+(\d+):\s+Pass", line, re.IGNORECASE)
        if m:
            tid = int(m.group(1))
            if tid in results: results[tid]["status"] = "PASS"

        m = re.search(r"Test\s+(\d+):\s+(Error|Failed)", line, re.IGNORECASE)
        if m:
            tid = int(m.group(1))
            if tid in results: results[tid]["status"] = "FAIL"

        m = re.search(r"Test No\.\s+(\d+)\s+-\s+passed", line, re.IGNORECASE)
        if m:
            tid = int(m.group(1))
            if tid in results: results[tid]["status"] = "PASS"

        m = re.search(r"Test No\.\s+(\d+)\s+-\s+failed", line, re.IGNORECASE)
        if m:
            tid = int(m.group(1))
            if tid in results: results[tid]["status"] = "FAIL"

        if re.search(r"\$error|Error\s*-|ERROR", line, re.IGNORECASE):
            for tid in results:
                if results[tid]["status"] in ("UNKNOWN", "FAIL"):
                    results[tid]["errors"].append(line.strip())

    return results

# =============================================================================
# LOG WRITERS
# =============================================================================

def write_short_log(results, log_path, run_info):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("  TEST RESULTS (SHORT LOG)\n")
        f.write("=" * 60 + "\n")
        f.write("  Date  : {}\n".format(ts))
        f.write("  Tests : {}\n".format(run_info.get("test_ids", "N/A")))
        f.write("=" * 60 + "\n\n")
        pc = fc = uc = 0
        cur_cat = None
        for tid, r in sorted(results.items()):
            if r["category"] != cur_cat:
                cur_cat = r["category"]
                f.write("\n  --- {} ---\n".format(cur_cat))
            s = r["status"]
            if s == "PASS":   pc += 1
            elif s == "FAIL": fc += 1
            else:             uc += 1
            f.write("  [{}] Test {} - {}\n".format(s, tid, r["name"]))
            if r.get("params_text"):
                f.write("         params: {}\n".format(r["params_text"]))
        f.write("\n" + "=" * 60 + "\n")
        f.write("  TOTAL: {} PASSED | {} FAILED | {} UNKNOWN\n".format(pc, fc, uc))
        f.write("=" * 60 + "\n")
    print("[LOG] Short log: {}".format(log_path))

def write_extended_log(results, raw_output, log_path, run_info):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("  TEST RESULTS (EXTENDED LOG)\n")
        f.write("=" * 60 + "\n")
        f.write("  Date  : {}\n".format(ts))
        f.write("  Tests : {}\n".format(run_info.get("test_ids", "N/A")))
        f.write("=" * 60 + "\n\n")
        for tid, r in sorted(results.items()):
            f.write("  Test {:<3} [{}] {}\n".format(tid, r["status"], r["name"]))
            if r.get("params_text"):
                f.write("         params: {}\n".format(r["params_text"]))
            if r["errors"]:
                for e in r["errors"]: f.write("    ERR: {}\n".format(e))
        f.write("\n\n--- FULL OUTPUT ---\n\n")
        f.write(raw_output)
    print("[LOG] Extended log: {}".format(log_path))

# =============================================================================
# MAIN RUNNER
# =============================================================================

def run(tests="all", order="default", repeat=1,
        stdout=True, short_log=True, extended_log=True,
        param_overrides=None):
    """
    tests           : "all" | category name | list of test IDs
    order           : "default" | "random" | list of IDs
    repeat          : int or "endless"
    param_overrides : optional {test_id: {param_name: {"mode": "manual"|"random",
                                                       "value": int}}}
                      Only applies to tests listed in TEST_PARAM_SPECS.
    """
    if tests == "all":
        selected = get_all_tests()
    elif isinstance(tests, str):
        selected = get_tests_by_category(tests)
        if not selected:
            print("[ERROR] Unknown category: '{}'. Available: {}".format(
                tests, ", ".join('"{}"'.format(c) for c in CATEGORIES)))
            return
    elif isinstance(tests, list):
        selected = []
        for t in tests:
            found = get_test(t)
            if found: selected.append(found)
            else: print("[WARNING] Test {} not found".format(t))
    else:
        print("[ERROR] Invalid tests argument"); return

    if not selected:
        print("[ERROR] No tests selected."); return

    if order == "random":
        random.shuffle(selected); print("[INFO] Order: RANDOM")
    elif isinstance(order, list):
        m = {t["id"]: t for t in selected}
        selected = [m[i] for i in order if i in m]
        print("[INFO] Order: CUSTOM")
    else:
        print("[INFO] Order: DEFAULT")

    print("\n[INFO] Tests to run ({}):".format(len(selected)))
    for t in selected:
        print("       - Test {}: {} ({})".format(t["id"], t["task_name"], t["category"]))

    tb_path, fl_path, resolved_map = generate_tb_and_filelist(
        selected, param_overrides=param_overrides)

    iterations = ENDLESS_LOOP_LIMIT if repeat == "endless" else int(repeat)
    print("[INFO] Mode: {}".format("ENDLESS" if repeat == "endless" else "REPEAT x{}".format(iterations)))

    all_results = {}
    ts = datetime.datetime.now().strftime("%d.%m.%Y_%H-%M-%S")
    run_info = {"test_ids": [t["id"] for t in selected], "iterations": iterations}

    for i in range(iterations):
        if iterations > 1:
            print("\n" + "=" * 60)
            print("  ITERATION {} of {}".format(i+1, iterations))
            print("=" * 60)

        raw = compile_and_run(fl_path, verbose_stdout=stdout)
        if raw is None:
            print("[ERROR] Simulation failed on iteration {}".format(i+1)); break

        results = parse_results(raw, selected,
                                resolved_map=resolved_map,
                                param_overrides=param_overrides)
        all_results[i+1] = results

        print("\n[RESULTS]")
        for tid, r in sorted(results.items()):
            print("  Test {:<3} [{}] {}".format(tid, r["status"], r["name"]))
            if r.get("params_text"):
                print("           params: {}".format(r["params_text"]))

        suf = "_{}".format(i+1) if iterations > 1 else ""
        if short_log:
            write_short_log(results, os.path.join(LOG_DIR, "short_log_{}{}.txt".format(ts, suf)), run_info)
        if extended_log:
            write_extended_log(results, raw, os.path.join(LOG_DIR, "extended_log_{}{}.txt".format(ts, suf)), run_info)

    print("\n[INFO] Done.")
    return all_results

if __name__ == "__main__":
    print_available_tests()
    print("Use run_interface.py to run tests.")
