# VLSI Project_B
Full Chip Verification Environment

# User Manual

Hey, welcome.

This manual explains how to use the test runner with your own SystemVerilog
project. It is written for someone who does not already know this project, so
follow the sections in order the first time you set it up.


## Table Of Contents

- [What This Project Does](#what-this-project-does)
- [1. Required Project Structure](#1-required-project-structure)
- [2. Where To Put `python_runner`](#2-where-to-put-python_runner)
- [3. Configuring `run_tests.py`](#3-configuring-run_testspy)
- [4. Helper Tasks In `SETUP_TASKS`](#4-helper-tasks-in-setup_tasks)
- [5. Running From The CLI](#5-running-from-the-cli)
- [6. Running From The GUI](#6-running-from-the-gui)
- [7. Adding Parameters To A Test](#7-adding-parameters-to-a-test)
  - [7.1 Where The Feature Lives](#71-where-the-feature-lives)
  - [7.2 The `TEST_PARAM_SPECS` Entry Format](#72-the-test_param_specs-entry-format)
  - [7.3 Worked Example](#73-worked-example)
  - [7.4 Matching SV Task](#74-matching-sv-task)
  - [7.5 In The CLI](#75-in-the-cli)
  - [7.6 In The GUI](#76-in-the-gui)
  - [7.7 In The Logs](#77-in-the-logs)
  - [7.8 Checklist](#78-checklist)
- [8. Filelist And Generated Filelist](#8-filelist-and-generated-filelist)
- [9. User Categories JSON File](#9-user-categories-json-file)
- [10. Using This With A Non-IRIS Project](#10-using-this-with-a-non-iris-project)
- [11. Quick Setup Checklist](#11-quick-setup-checklist)


## What This Project Does

This project lets you run SystemVerilog tests from either:

- a **CLI** - Command Line Interface, used from the terminal.
- a **GUI** - Graphical User Interface, opened in a browser.

The project was built mainly for the **IRIS** project in the VLSI Lab, but it
can also be used for other projects if they follow the same basic structure.

The main idea is simple: instead of running every test in the testbench every
time, you choose the tests you want to run. The Python runner then creates a
new generated testbench that contains only those selected tests, compiles it,
runs the simulation, and checks the pass/fail results.

This saves time, keeps the logs cleaner, and makes it easier to debug a
specific part of the design.


## 1. Required Project Structure

The Python scripts discover the tests automatically. To make that work, the
project files need to be organized in a clear way.


### 1.1 DUT Files

Put your DUT (Design Under Test) SystemVerilog files in one main folder.

In this project, that folder is:

```text
RTL/
```

It is better to keep the DUT files together because the filelist and the
runner can find them more easily.


### 1.2 Test Files

Put each test in a separate `.sv` file inside a dedicated tests folder.

In this project, the tests folder is:

```text
functions/tests_separate/
```

Use file names that include the test number and a short name:

```text
test_01_check_serial_output_po.sv
test_02_read_all_control_registers_po_values.sv
test_10_16_write_read_dead_beef_from_host.sv
```

At the top of each test file, write a comment with the test number and a short
description. The runner uses this line to identify the test.

Example:

```systemverilog
// Test No. 2 - Read all Control registers and compare to the PO default values.
task read_all_control_registers_po_values(...);
   ...
endtask
```

If one test file represents two test IDs, write them with a slash:

```systemverilog
// Test No. 10/16 - Host read address 0; write DEAD_BEEF_BAD4_F00D; read and compare.
```

This is useful when the same task runs in two modes, for example regular
memory and memory-on-flops.


### 1.3 `tests_include.sv`

In the same tests folder, create a file called:

```text
tests_include.sv
```

This file should include all the separate test files:

```systemverilog
`include "/abs/path/to/tests_separate/test_01_check_serial_output_po.sv"
`include "/abs/path/to/tests_separate/test_02_read_all_control_registers_po_values.sv"
`include "/abs/path/to/tests_separate/test_10_16_write_read_dead_beef_from_host.sv"
```

The idea is that the main testbench only needs to include one file, and that
one file includes all the tests.


### 1.4 Include The Tests In The Main Testbench

In your main testbench, include `tests_include.sv`.

Example:

```systemverilog
`include "/abs/path/to/tests_separate/tests_include.sv"
```

In this project, the main testbench is:

```text
RTL/top_iris_tb.sv
```


### 1.5 Call The Test Tasks In The Testbench

Inside the main testbench, after your reset and setup code, call the test
tasks one after another.

You can divide tests into categories by putting a starred comment above each
group. The runner reads these comments and turns them into categories in the
CLI and GUI.

The category line must look like this:

```systemverilog
//******************** Registers Tests ***************************//
```

That is: starts with `//`, then any number of `*`, then the category name,
then `*`, and ends with `//`. The runner picks up the text between the stars
as the category name.

In the IRIS testbench you will also see two extra all-stars lines above and
below the name line - those are just for visual decoration and the script
ignores them. Only the line with the category name matters.

Full example as it appears in the testbench:

```systemverilog
//*****************************************************************//
//******************** Registers Tests ***************************//
//*****************************************************************//

// Test No. 2 - Read all Control registers and compare to the PO default values.
read_all_control_registers_po_values(returned_data, expected_data, FALSE);

// Test No. 3 - Write data to all Control registers, then read back.
write_read_all_control_registers(returned_data, FALSE);
```

In this example, the runner creates a category called `Registers Tests` and
puts every task call below it (until the next category line) into that
category.

End the simulation with:

```systemverilog
$finish;
```

The script uses `$finish;` to know where the test section ends.


### 1.6 Pass / Fail Messages

If you want the Python runner to understand whether each test passed or
failed, print the result in this format:

```systemverilog
if (pass) $display("Test No. 2 - passed!!");
else      $display("Test No. 2 - failed!!");
```

The existing tests in `functions/tests_separate/` already use this style, so
you can copy from them.

The parser also understands these formats:

```text
Test 2: Pass
Test 2: Failed
```

If the test prints something else, the runner may show the result as
`UNKNOWN`.


## 2. Where To Put `python_runner`

Put the `python_runner/` folder inside your project root.

The recommended structure is:

```text
my_project/
|-- RTL/
|-- functions/
|   `-- tests_separate/
|-- filelist
`-- python_runner/        <-- put it here
    |-- run_tests.py
    |-- run_interface.py
    |-- run_gui.py
    |-- generated/
    `-- logs/
```

The `generated/` folder is used for the generated testbench and generated
filelist.

The `logs/` folder is used for short and extended run logs.

If these folders are missing, the script will create them when needed.


## 3. Configuring `run_tests.py`

Open:

```text
python_runner/run_tests.py
```

Near the top of the file there is a configuration block. This is the main
place you need to edit when moving the runner to another project.

Current example:

```python
PROJECT_DIR  = "/users/epstmh/Project_B/rev12"
TB_FILE      = os.path.join(PROJECT_DIR, "RTL", "top_iris_tb.sv")
TESTS_DIR    = os.path.join(PROJECT_DIR, "functions", "tests_separate")
FILELIST_SRC = os.path.join(PROJECT_DIR, "filelist")
LOG_DIR      = os.path.join(PROJECT_DIR, "python_runner", "logs")
GEN_DIR      = os.path.join(PROJECT_DIR, "python_runner", "generated")
GEN_TB       = os.path.join(GEN_DIR, "generated_tb.sv")
GEN_FILELIST = os.path.join(GEN_DIR, "filelist_generated")
```


### What `os.path.join` Means

`os.path.join` builds a path from smaller parts.

Example:

```python
os.path.join("/a/b", "c", "d.sv")
```

becomes:

```text
/a/b/c/d.sv
```

So instead of writing one long path manually every time, the script builds the
paths from `PROJECT_DIR`.


### What To Change

| Variable | Meaning | What You Should Change |
|---|---|---|
| `PROJECT_DIR` | The absolute path to your project root. | Change this to your own project path. |
| `TB_FILE` | The main testbench file. | Change the folder or file name if your testbench is not `RTL/top_iris_tb.sv`. |
| `TESTS_DIR` | The folder containing the separate `test_*.sv` files. | Point this to your tests folder. |
| `FILELIST_SRC` | The original VCS filelist. | Point this to your real filelist. The script reads it but does not edit it. |
| `LOG_DIR` | Where run logs are saved. | Usually leave this as `python_runner/logs`. |
| `GEN_DIR` | Where generated files are saved. | Usually leave this as `python_runner/generated`. |
| `GEN_TB` | The generated testbench path. | Usually leave this as-is. |
| `GEN_FILELIST` | The generated filelist path. | Usually leave this as-is. |

Also check `VCS_BASE_CMD` in the same file. This is the VCS compile command.
If your project needs different `+define+...` options or different
`+incdir+...` include paths, edit them there.


## 4. Helper Tasks In `SETUP_TASKS`

In `run_tests.py`, you will also see:

```python
SETUP_TASKS = frozenset([
    "setup_memory_mode", "setup_to_1adc", "setup_to_4adcs",
    "setup_for_general_startup", "setup_for_flops_memory",
    "setup_to_memory_on_flops_function", "setup_to_memory_function",
    "clean_up_buffers",
])
```

These are helper tasks. They are called from the testbench, but they are not
real tests.

The runner scans the testbench and looks for task calls. Without
`SETUP_TASKS`, it may think helper tasks are tests. This list tells the runner
to ignore them.

What to do for your project:

- Add any helper/setup task names that should not appear as tests.
- Remove IRIS-specific helper names that you do not use.


## 5. Running From The CLI

Open a terminal and go into the `python_runner/` folder:

```bash
cd python_runner
python3 run_interface.py
```

You will see a menu.

| Option | Meaning |
|---|---|
| `1. Show all available tests` | Prints all tests the script discovered, grouped by category. |
| `2. Show auto-discovered categories` | Shows categories found from the starred comments in the testbench. |
| `3. Show saved user categories` | Shows categories that you created yourself. |
| `4. Create user category` | Lets you save a custom group of tests by name. |
| `5. Delete user category` | Deletes a saved user category. |
| `6. Run tests` | Selects and runs tests. |
| `0. Exit` | Closes the CLI. |

When creating a user category, you can enter test IDs like this:

```text
1-3, 5, 10-12
```

This means tests 1, 2, 3, 5, 10, 11, and 12.

When you choose `Run tests`, the CLI asks you:

1. What to run: all tests, an auto category, a user category, or specific IDs.
2. Log type: short log only, or extended log.
3. Order: default order or random order.
4. Repeat count: a number, or `endless`.
5. Whether to show simulation output in the terminal.

After that, the script generates the testbench, generates the filelist,
compiles with VCS, runs the simulation, prints the results, and writes logs to:

```text
python_runner/logs/
```


## 6. Running From The GUI

Open a terminal and go into the `python_runner/` folder:

```bash
cd python_runner
python3 run_gui.py
```

The script prints a link like:

```text
Open in browser: http://localhost:8080
```

If port `8080` is already taken, the GUI automatically tries the next ports
(`8081`, `8082`, ...). Always use the exact URL printed in the terminal.


### How To Open The Link In Linux

In a Linux terminal you usually cannot just left-click the link. Use one of
the methods below.


**Method 1 - Ctrl + Click**

In most Linux terminals (gnome-terminal, konsole, xterm, MobaXterm, etc.)
you can hold **Ctrl** and **left-click** the URL. That opens it in your
default browser.

In some terminals it is **Ctrl + Shift + Click** instead.


**Method 2 - Right-click the link**

Right-click on the URL in the terminal and choose `Open Link` (or
`Follow Link`, depending on the terminal).


**Method 3 - Copy and paste**

Highlight the URL with the mouse, copy it (`Ctrl + Shift + C` in most Linux
terminals), and paste it into your browser address bar
(`Ctrl + V` or `Ctrl + Shift + V`).


**Method 4 - Open it from the command line**

In a second terminal on the same machine, run any of:

```bash
xdg-open http://localhost:8080
```

```bash
firefox http://localhost:8080 &
```

```bash
google-chrome http://localhost:8080 &
```

`xdg-open` is the most universal one - it opens the URL in whatever browser
the system is configured to use.


> [!TIP]
> **When You Are Connected Over SSH**
> 
> If you ran `python3 run_gui.py` on a remote Linux server through SSH, the
> server has no display, so opening the link directly on the server will not
> work.
> 
> You have to forward the port to your own machine first.
> 
> On your **local** machine, open a new terminal and run:
> 
> ```bash
> ssh -L 8080:localhost:8080 user@server
> ```
> 
> Replace `user@server` with your real SSH login. If the GUI is using a
> different port, replace both `8080` numbers with that port.
> 
> Keep this SSH session open. Then on your **local** machine, open a browser
> and go to:
> 
> ```text
> http://localhost:8080
> ```
> 
> The traffic is tunneled through SSH to the server, so the GUI shows up on
> your local browser.


### GUI Layout

**Left side - Test Selection**

- Shows all test categories.
- Lets you select a full category or individual tests.
- Has `Select All` and `Deselect All` buttons.

**Right side - Run Settings**

- Choose default or random order.
- Choose repeat count, for example `1`, `5`, or `endless`.
- Choose log type: short only or both short and extended.
- Choose whether to show simulation output.
- Press the green `RUN TESTS` button to start.

**Right side - User Categories**

- Save the currently selected tests as a named category.
- Load a saved category.
- Delete a saved category.

The CLI and GUI use the same user category file, so a category created in the
GUI will also appear in the CLI.

**Bottom panel - Output**

- Shows live output from the run.
- PASS lines appear in green.
- FAIL and ERROR lines appear in red.
- INFO lines appear in blue.

**Bottom status bar**

- Shows if the GUI is ready, running, or done.
- Shows how many tests are available.


## 7. Adding Parameters To A Test

This section is **optional**. Use it only if some of your tests need to be
called with arguments. If all your tests are parameter-less, skip ahead.

What the feature gives you:

- For each declared parameter, pick `Random` (auto-generated) or `Manual`
  (user-typed) at run time.
- Each parameter has a `min` / `max` range, validated by the GUI and CLI.
- A parameter can use another parameter's chosen value as its `min` or `max`
  (chained reference).


### 7.1 Where The Feature Lives

The feature is in a second copy of the runner:

```text
python_runner_with_params/
```

It works exactly like `python_runner/` (same CLI, same GUI, same testbench
layout). The only difference is one extra dictionary in `run_tests.py`:
`TEST_PARAM_SPECS`. The two folders are independent and each has its own
`generated/` and `logs/`.


### 7.2 The `TEST_PARAM_SPECS` Entry Format

Open `python_runner_with_params/run_tests.py` and find:

```python
TEST_PARAM_SPECS = {
    # test_id : { ... },
}
```

Each key is a test ID. A minimal entry looks like this:

```python
<test_id>: {
    "task_name": "<sv_task_name>",
    "params": [
        {"name": "<arg1>", "type": "int",   "min": <int>, "max": <int>},
        {"name": "<arg2>", "type": "logic", "width": "[N:0]",
         "min": <int_or_param_name>, "max": <int_or_param_name>},
    ],
},
```

Field reference:

| Field | Meaning |
|---|---|
| `task_name` | Exact SV task name (must match the `task <name>(...)` line). |
| `params` | List, in the **same order** as the SV task arguments. |
| `name` | Display name for the argument (used in the GUI/CLI/logs). |
| `type` | `"int"` or `"logic"`. Display only. |
| `width` | Optional bit width like `"[10:0]"`. Display only. |
| `min` | An int, or the `name` of an earlier param in the same list. |
| `max` | An int, or the `name` of an earlier param in the same list. |

Order matters for two reasons: the SV call is emitted in list order, and a
parameter can only reference earlier parameters in its `min`/`max`.


### 7.3 Worked Example

Below is one entry from `TEST_PARAM_SPECS`. It exercises every feature: four
parameters, two types, custom widths, fixed-int ranges, and a chained
reference.

```python
23: {
    "task_name": "hw_write_ds_one_partial_buffer",
    "params": [
        {"name": "partial_address",  "type": "logic", "width": "[10:0]",
         "min": 10, "max": 2048},
        {"name": "number_of_cycles", "type": "int",
         "min": "partial_address", "max": 5000},
        {"name": "param",            "type": "int",
         "min": 100, "max": 5000},
        {"name": "ds_number",        "type": "logic", "width": "[11:0]",
         "min": 8, "max": 4096},
    ],
},
```

Reading it:

- Test `23` will be called as `hw_write_ds_one_partial_buffer(...)` with
  four arguments, in the order listed.
- `number_of_cycles.min` is `"partial_address"` - so its effective `min` is
  whatever value `partial_address` got. If `partial_address = 1000`, the
  range becomes `[1000..5000]`.


### 7.4 Matching SV Task

The SV task in your tests folder must accept the arguments in the same order:

```systemverilog
task hw_write_ds_one_partial_buffer(
    input logic [10:0] partial_address,
    input int          number_of_cycles,
    input int          param,
    input logic [11:0] ds_number);
    // ...
endtask
```

The matching is **by position**, not by name. The names in the spec are only
labels for display.


### 7.5 In The CLI

When the test is selected and you choose `Run tests`, the CLI walks each
parameter:

```text
------------------------------------------------------------
  Test 23 parameters  (hw_write_ds_one_partial_buffer)
------------------------------------------------------------

    Param 'partial_address' (logic [10:0])  range: [10..2048]
      1. Manual value
      2. Random
    Choose (1/2) [default: 2]: 1
    Value for 'partial_address' [10..2048] (b=back): 1000
    -> Manual: partial_address = 1000

    Param 'number_of_cycles' (int)  range: [1000..5000]
      1. Manual value
      2. Random
    Choose (1/2) [default: 2]: 2
    -> Random: number_of_cycles = 3120  (rolled in [1000..5000])

    ...

    Summary for Test 23:
      [MANUAL] partial_address    = 1000
      [RANDOM] number_of_cycles   = 3120
      [MANUAL] param              = 2500
      [RANDOM] ds_number          = 2048
```

The range for `number_of_cycles` is shown as `[1000..5000]` (not
`[partial_address..5000]`) because the reference is resolved live, right
after `partial_address` is set.


### 7.6 In The GUI

```bash
cd python_runner_with_params
python3 run_gui.py
```

Tests that have a parameter spec get a small triangle (`>`) next to the
task name. Click it to expand a per-test settings panel.

You will see this window pop up:

<img width="1015" height="192" alt="Screenshot 2026-05-04 195130" src="https://github.com/user-attachments/assets/2d104e30-03e0-4587-8215-7aa5bfff362b" />




Visual cues in the real GUI:

- Random rows are tinted blue, manual rows are tinted yellow.
- A range whose `min` or `max` is a reference is shown in orange, so you can
  see at a glance that it depends on another parameter.
- An out-of-range manual value turns the input red and shakes it.
- `re-roll` redraws a random value and refreshes any dependent parameter.



<img width="689" height="158" alt="Screenshot 2026-05-08 193710" src="https://github.com/user-attachments/assets/803be75e-4a42-46e5-a5ce-d75ec6c0371d" />

```text
•	Blue Tint: Parameters set to 'Random'.
•	Yellow Tint: Parameters set to 'Manual'.
•	Orange Text: Indicates a chained reference range.
•	Red/Shaking Box: Indicates an out-of-range manual entry.
```

Pressing `RUN TESTS` with the values above puts this line into the generated
testbench:

```systemverilog
hw_write_ds_one_partial_buffer(1000, 3120, 2500, 2048);
```


### 7.7 In The Logs

The short and extended logs both record the values used, so you can
reproduce a run:

```text
  [PASS] Test 23 - hw_write_ds_one_partial_buffer
         params: partial_address=1000[MANUAL], number_of_cycles=3120[RANDOM], param=2500[MANUAL], ds_number=2048[RANDOM]
```


### 7.8 Checklist

- [ ] The SV task accepts the arguments in the order you want.
- [ ] You added an entry to `TEST_PARAM_SPECS` keyed by the test number.
- [ ] `task_name` matches the SV task name exactly.
- [ ] `params` is in the same order as the SV arguments.
- [ ] Each `min` / `max` is either an int or the `name` of an earlier param.
- [ ] You opened the GUI, expanded the test, and the rows appear correctly.
- [ ] After a run, `python_runner_with_params/generated/generated_tb.sv`
      shows the expected call line.


## 8. Filelist And Generated Filelist

Your normal `filelist` is the file that VCS uses to know which design files
and testbench files to compile.

The runner does not edit your original filelist.

Instead, it does this:

1. Reads your original `filelist`.
2. Finds the line that contains the original testbench name.
3. Replaces that line with the generated testbench path.
4. Writes the result to:

```text
python_runner/generated/filelist_generated
```

The generated testbench is written to:

```text
python_runner/generated/generated_tb.sv
```

VCS then compiles using `filelist_generated`.

So if something looks wrong, check the generated files first. They show
exactly what the runner actually compiled.


## 9. User Categories JSON File

User categories are saved here:

```text
python_runner/user_categories.json
```

The file is a simple JSON file:

```json
{
  "my_category": [1, 3, 5],
  "regression_short": [2, 7, 10, 11]
}
```

You normally do not need to edit it manually. Use the CLI or GUI to create and
delete categories.

If you want to start fresh, you can delete this file and the runner will
create it again when you save a new category.


## 10. Using This With A Non-IRIS Project

This runner can be used outside the IRIS project, but you need to update the
project-specific parts.


### Things You Usually Need To Change

1. **Paths in `run_tests.py`**

   Change `PROJECT_DIR`, `TB_FILE`, `TESTS_DIR`, and `FILELIST_SRC` to match
   your project.

2. **`SETUP_TASKS`**

   Replace the IRIS helper task names with the helper tasks used in your own
   testbench.

3. **`VCS_BASE_CMD`**

   Update defines, include directories, and any VCS flags needed by your
   environment.

4. **Testbench categories**

   Put starred category comments above groups of task calls:

   ```systemverilog
   //******************** My Category ***************************//
   ```

5. **Pass / fail print format**

   Make sure each test prints:

   ```systemverilog
   $display("Test No. N - passed!!");
   $display("Test No. N - failed!!");
   ```


> [!NOTE]
> **About IRIS Memory Mode**
> 
> The IRIS testbench has special memory-mode behavior, including:
> 
> - a `for (int i = 0; i < 2; ...)` loop,
> - `memory_on_flops`,
> - `flops_tests_index`,
> - `setup_memory_mode(...)`.
> 
> The runner knows how to detect this structure.
> 
> If your project does not use this memory-mode structure, that is okay. Just
> call your tests normally in the testbench. The runner will treat them as
> standalone tests.


## 11. Quick Setup Checklist

Before running for the first time, check this:

- [ ] DUT files are in one folder and listed in the filelist.
- [ ] Each test is in a separate `test_*.sv` file.
- [ ] Each test file starts with `// Test No. N - description`.
- [ ] `tests_include.sv` includes all test files.
- [ ] The main testbench includes `tests_include.sv`.
- [ ] The main testbench calls all test tasks.
- [ ] Tests are grouped using starred category comments.
- [ ] The testbench ends with `$finish;`.
- [ ] Each test prints a clear pass/fail message.
- [ ] `python_runner/` is inside the project.
- [ ] `run_tests.py` paths are updated.
- [ ] `SETUP_TASKS` contains only helper tasks that should be ignored.
- [ ] `VCS_BASE_CMD` matches your simulation environment.

After that, run one of these:

```bash
python3 run_interface.py
```

or:

```bash
python3 run_gui.py
```

That is it. Choose the tests you want, run them, and check the logs.
