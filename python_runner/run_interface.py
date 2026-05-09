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
import datetime
from run_tests import (
    run, print_available_tests, get_all_tests, get_tests_by_category,
    get_test, TEST_LIST, CATEGORIES
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


def run_with_options(tests_arg):
    """Common flow: pick log type, order, repeat, then run."""
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
        stdout=stdout, short_log=short_log, extended_log=extended_log)


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
