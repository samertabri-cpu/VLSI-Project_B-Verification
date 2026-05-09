#!/usr/bin/env python3
"""
Interactive Test Runner Interface
==================================
Menu-driven CLI for managing test categories, selecting tests, and running them.
User-defined categories are saved to disk for reuse across sessions.
Python 3.6 compatible.
"""

import os
import json
import random
import datetime
from run_tests import (
    run, print_available_tests, get_all_tests, get_tests_by_category,
    get_test, TEST_LIST, CATEGORIES, TEST_PARAM_SPECS, get_test_param_spec,
    format_param_range_text
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_FILE = os.path.join(SCRIPT_DIR, "user_categories.json")

LINE = "=" * 65
THIN = "-" * 65


def load_user_categories():
    if not os.path.isfile(CATEGORIES_FILE):
        return {}
    try:
        with open(CATEGORIES_FILE, "r") as f:
            return json.load(f)
    except (ValueError, IOError):
        return {}


def save_user_categories(cats):
    with open(CATEGORIES_FILE, "w") as f:
        json.dump(cats, f, indent=2)


def input_stripped(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def parse_id_range(text):
    """Parse '1-3, 5, 10-12' into a sorted list of ints."""
    ids = []
    for part in text.replace(",", " ").split():
        part = part.strip()
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                lo, hi = int(bounds[0]), int(bounds[1])
                ids.extend(range(lo, hi + 1))
            except (ValueError, IndexError):
                pass
        else:
            try:
                ids.append(int(part))
            except ValueError:
                pass
    return sorted(set(ids))


def show_auto_categories():
    print("\n" + LINE)
    print("  AUTO-DISCOVERED CATEGORIES (from project files)")
    print(LINE)
    for idx, (cat, tids) in enumerate(CATEGORIES.items(), 1):
        print("  {:2d}. {} ({} tests: {})".format(
            idx, cat, len(tids), ", ".join(str(t) for t in sorted(tids))))
    print(LINE)


def show_user_categories(user_cats):
    if not user_cats:
        print("\n  [No saved user categories yet]")
        return
    print("\n" + LINE)
    print("  SAVED USER CATEGORIES")
    print(LINE)
    for idx, (name, tids) in enumerate(sorted(user_cats.items()), 1):
        print("  {:2d}. {} ({} tests: {})".format(
            idx, name, len(tids), ", ".join(str(t) for t in sorted(tids))))
    print(LINE)


def create_category(user_cats):
    print("\n" + THIN)
    print("  CREATE NEW CATEGORY")
    print(THIN)

    all_ids = sorted(t["id"] for t in TEST_LIST)
    print("  Available test IDs: {}".format(", ".join(str(i) for i in all_ids)))

    name = input_stripped("\n  Category name: ")
    if not name:
        print("  [Cancelled]")
        return user_cats

    if name in user_cats:
        overwrite = input_stripped("  '{}' already exists. Overwrite? (y/n): ".format(name))
        if overwrite.lower() != "y":
            print("  [Cancelled]")
            return user_cats

    print("  Enter test IDs (ranges ok, e.g. '1-3, 5, 10-12'):")
    raw = input_stripped("  > ")
    ids = parse_id_range(raw)

    valid_set = set(all_ids)
    invalid = [i for i in ids if i not in valid_set]
    ids = [i for i in ids if i in valid_set]

    if invalid:
        print("  [Warning] These IDs don't exist and were skipped: {}".format(invalid))
    if not ids:
        print("  [Error] No valid test IDs. Category not created.")
        return user_cats

    user_cats[name] = ids
    save_user_categories(user_cats)
    print("  [OK] Category '{}' saved with tests: {}".format(name, ids))
    return user_cats


def delete_category(user_cats):
    if not user_cats:
        print("\n  [No user categories to delete]")
        return user_cats

    show_user_categories(user_cats)
    print("\n  Enter category name (or number) to delete, or 'all' to clear everything:")
    choice = input_stripped("  > ")

    if choice.lower() == "all":
        confirm = input_stripped("  Delete ALL user categories? (y/n): ")
        if confirm.lower() == "y":
            user_cats.clear()
            save_user_categories(user_cats)
            print("  [OK] All user categories deleted.")
        else:
            print("  [Cancelled]")
        return user_cats

    names = sorted(user_cats.keys())
    target = None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(names):
            target = names[idx]
    except ValueError:
        if choice in user_cats:
            target = choice

    if target is None:
        print("  [Error] Category '{}' not found.".format(choice))
        return user_cats

    confirm = input_stripped("  Delete '{}'? (y/n): ".format(target))
    if confirm.lower() == "y":
        del user_cats[target]
        save_user_categories(user_cats)
        print("  [OK] Category '{}' deleted.".format(target))
    else:
        print("  [Cancelled]")
    return user_cats


def choose_log_type():
    print("\n  Log type:")
    print("    1. Short log only")
    print("    2. Extended log (includes short + full output)")
    choice = input_stripped("  Choose (1/2) [default: 1]: ")
    if choice == "2":
        return True, True
    return True, False


def choose_order():
    print("\n  Test order:")
    print("    1. Default")
    print("    2. Random")
    choice = input_stripped("  Choose (1/2) [default: 1]: ")
    if choice == "2":
        return "random"
    return "default"


def choose_repeat():
    raw = input_stripped("\n  Repeat count (number or 'endless') [default: 1]: ")
    if not raw:
        return 1
    if raw.lower() == "endless":
        return "endless"
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        return 1


def choose_stdout():
    choice = input_stripped("\n  Show simulation output in terminal? (y/n) [default: y]: ")
    return choice.lower() != "n"


def _expand_tests_arg(tests_arg):
    """Expand the tests argument (all/category/list) to a list of test IDs."""
    if tests_arg == "all":
        return [t["id"] for t in get_all_tests()]
    if isinstance(tests_arg, list):
        return list(tests_arg)
    if isinstance(tests_arg, str):
        return [t["id"] for t in get_tests_by_category(tests_arg)]
    return []


def _param_type_text(p):
    """Render the parameter type: 'int' or 'logic [10:0]'."""
    t = p.get("type", "int")
    w = p.get("width")
    if w:
        return "{} {}".format(t, w)
    return t


def _resolved_bound(bound, concrete_vals, fallback):
    """Resolve a min/max that may be a literal int or reference another
    param by name. Uses already-resolved concrete values (manual entries
    and pre-rolled random values); falls back to the given spec value
    when the referenced param has not been resolved yet.
    """
    if isinstance(bound, int):
        return bound
    if isinstance(bound, str):
        if bound in concrete_vals:
            return concrete_vals[bound]
        return fallback
    return fallback


def prompt_test_params(test_ids):
    """For each selected test that has a parameter spec, ask the user to pick
    manual value or random per parameter. Random values are rolled
    immediately at selection time and echoed to the user, so later manual
    prompts can be validated against the *actual* value of any referenced
    random parameter (this fixes the case where, e.g., a random
    partial_address could end up larger than a manual number_of_cycles).

    Returns param_overrides dict. Random choices are returned as
    {"mode": "random", "value": <rolled>} so the engine uses the same
    values the user saw.
    """
    overrides = {}
    for tid in test_ids:
        spec = get_test_param_spec(tid)
        if not spec:
            continue

        print("\n" + THIN)
        print("  Test {} parameters  ({})".format(tid, spec["task_name"]))
        print(THIN)
        print()

        test_overrides = {}
        concrete_vals = {}
        param_modes = {}
        spec_params_by_name = {x["name"]: x for x in spec["params"]}

        for idx, p in enumerate(spec["params"]):
            if idx > 0:
                print()
            name = p["name"]
            type_text = _param_type_text(p)

            lo_spec = p["min"] if isinstance(p["min"], int) else \
                spec_params_by_name[p["min"]]["min"]
            hi_spec = p["max"] if isinstance(p["max"], int) else \
                spec_params_by_name[p["max"]]["max"]
            eff_lo = _resolved_bound(p["min"], concrete_vals, lo_spec)
            eff_hi = _resolved_bound(p["max"], concrete_vals, hi_spec)
            live_rng = "[{}..{}]".format(eff_lo, eff_hi)

            print("    Param '{}' ({})  range: {}".format(name, type_text, live_rng))
            while True:
                print("      1. Manual value")
                print("      2. Random")
                choice = input_stripped("    Choose (1/2) [default: 2]: ")

                if choice == "1":
                    back_to_mode = False
                    while True:
                        raw = input_stripped(
                            "    Value for '{}' [{}..{}] (b=back): ".format(
                                name, eff_lo, eff_hi))
                        if raw.lower() == "b":
                            back_to_mode = True
                            break
                        try:
                            val = int(raw)
                        except ValueError:
                            print("    [Invalid integer, try again, or type 'b' to go back and pick Random]")
                            continue
                        if val < eff_lo or val > eff_hi:
                            print("    [Out of range {}, try again, or 'b' to go back and pick Random]".format(live_rng))
                            continue
                        test_overrides[name] = {"mode": "manual", "value": val}
                        concrete_vals[name] = val
                        param_modes[name] = "manual"
                        print("    -> Manual: {} = {}".format(name, val))
                        break
                    if back_to_mode:
                        continue
                    break
                else:
                    if eff_lo > eff_hi:
                        print("    [Error] Effective range {} is empty -- please enter manually".format(live_rng))
                        back_to_mode = False
                        while True:
                            raw = input_stripped(
                                "    Value for '{}' [{}..{}] (b=back): ".format(
                                    name, eff_lo, eff_hi))
                            if raw.lower() == "b":
                                back_to_mode = True
                                break
                            try:
                                val = int(raw)
                            except ValueError:
                                print("    [Invalid integer, try again, or type 'b' to go back]")
                                continue
                            test_overrides[name] = {"mode": "manual", "value": val}
                            concrete_vals[name] = val
                            param_modes[name] = "manual"
                            break
                        if back_to_mode:
                            continue
                        break
                    val = random.randint(eff_lo, eff_hi)
                    test_overrides[name] = {"mode": "random", "value": val}
                    concrete_vals[name] = val
                    param_modes[name] = "random"
                    print("    -> Random: {} = {}  (rolled in {})".format(name, val, live_rng))
                    break

        if test_overrides:
            overrides[tid] = test_overrides

        print()
        print("    {}".format(THIN[4:]))
        print("    Summary for Test {}:".format(tid))
        for p in spec["params"]:
            name = p["name"]
            mode = param_modes.get(name, "random")
            tag = "[MANUAL]" if mode == "manual" else "[RANDOM]"
            print("      {} {:<18} = {}".format(tag, name, concrete_vals.get(name, "?")))
    return overrides


def run_with_options(tests_arg):
    """Common flow: pick params first, then run options, then run."""
    test_ids = _expand_tests_arg(tests_arg)
    param_overrides = prompt_test_params(test_ids)
    short_log, extended_log = choose_log_type()
    order = choose_order()
    repeat = choose_repeat()
    stdout = choose_stdout()

    print("\n" + LINE)
    print("  STARTING RUN")
    print("  Tests    : {}".format(tests_arg))
    print("  Order    : {}".format(order))
    print("  Repeat   : {}".format(repeat))
    print("  Short log: {}".format(short_log))
    print("  Ext. log : {}".format(extended_log))
    print("  Stdout   : {}".format(stdout))
    print(LINE)

    confirm = input_stripped("\n  Proceed? (y/n) [default: y]: ")
    if confirm and confirm.lower() != "y":
        print("  [Cancelled]")
        return

    run(tests=tests_arg, order=order, repeat=repeat,
        stdout=stdout, short_log=short_log, extended_log=extended_log,
        param_overrides=param_overrides)


def select_and_run(user_cats):
    print("\n" + THIN)
    print("  SELECT TESTS TO RUN")
    print(THIN)
    print("    1. Run ALL tests")
    print("    2. Run by auto-discovered category")
    print("    3. Run by saved user category")
    print("    4. Run specific test IDs")
    print("    0. Back")

    choice = input_stripped("\n  Choose: ")

    if choice == "1":
        run_with_options("all")

    elif choice == "2":
        show_auto_categories()
        cat_names = list(CATEGORIES.keys())
        print("\n  Enter category name or number:")
        raw = input_stripped("  > ")
        target = None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(cat_names):
                target = cat_names[idx]
        except ValueError:
            for c in cat_names:
                if c.lower() == raw.lower():
                    target = c
                    break
        if target is None:
            print("  [Error] Category not found.")
            return
        print("  -> Running category: '{}'".format(target))
        run_with_options(target)

    elif choice == "3":
        if not user_cats:
            print("\n  [No user categories saved. Create one first.]")
            return
        show_user_categories(user_cats)
        names = sorted(user_cats.keys())
        print("\n  Enter category name or number:")
        raw = input_stripped("  > ")
        target = None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(names):
                target = names[idx]
        except ValueError:
            if raw in user_cats:
                target = raw
        if target is None:
            print("  [Error] Category '{}' not found.".format(raw))
            return
        ids = user_cats[target]
        print("  -> Running user category '{}': tests {}".format(target, ids))
        run_with_options(ids)

    elif choice == "4":
        all_ids = sorted(t["id"] for t in TEST_LIST)
        print("  Available: {}".format(", ".join(str(i) for i in all_ids)))
        raw = input_stripped("  Enter test IDs (e.g. '1-3, 10, 22'): ")
        ids = parse_id_range(raw)
        valid = set(all_ids)
        ids = [i for i in ids if i in valid]
        if not ids:
            print("  [Error] No valid IDs entered.")
            return
        print("  -> Running tests: {}".format(ids))
        run_with_options(ids)

    elif choice == "0":
        return
    else:
        print("  [Invalid choice]")


def main_menu():
    user_cats = load_user_categories()

    while True:
        print("\n" + LINE)
        print("  TEST RUNNER - MAIN MENU")
        print(LINE)
        print("    1. Show all available tests")
        print("    2. Show auto-discovered categories")
        print("    3. Show saved user categories")
        print("    4. Create user category")
        print("    5. Delete user category")
        print("    6. Run tests")
        print("    0. Exit")
        print(THIN)

        choice = input_stripped("  Choose: ")

        if choice == "1":
            print_available_tests()

        elif choice == "2":
            show_auto_categories()

        elif choice == "3":
            show_user_categories(user_cats)

        elif choice == "4":
            user_cats = create_category(user_cats)

        elif choice == "5":
            user_cats = delete_category(user_cats)

        elif choice == "6":
            select_and_run(user_cats)

        elif choice == "0":
            print("\n  Goodbye.\n")
            break

        else:
            print("  [Invalid choice, try again]")


if __name__ == "__main__":
    main_menu()
