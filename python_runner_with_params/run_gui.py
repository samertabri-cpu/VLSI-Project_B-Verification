#!/usr/bin/env python3
"""
Test Runner GUI (Web)
======================
Browser-based interface for selecting tests, managing categories, and running simulations.
Generic — works with any project that uses the run_tests.py engine.
Uses bottle (already installed, no extra deps).

Run:   python3 run_gui.py [port]
Open:  http://localhost:8080  (or the port you chose)
SSH:   ssh -L 8080:localhost:8080 user@server   then open localhost:8080 locally
"""

import os
import sys
import json
import random
import threading
import datetime

from bottle import Bottle, request, response, run as bottle_run

from run_tests import (
    TEST_LIST, CATEGORIES, generate_tb_and_filelist,
    compile_and_run, parse_results, write_short_log,
    write_extended_log, LOG_DIR, ENDLESS_LOOP_LIMIT,
    TEST_PARAM_SPECS, format_param_range_text,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_FILE = os.path.join(SCRIPT_DIR, "user_categories.json")

app = Bottle()

# ── Global run state (thread-safe via lock) ──────────────────────────

_lock = threading.Lock()
_state = {"running": False, "output": []}


def _log(msg):
    with _lock:
        _state["output"].append(msg)


class _LogCapture(object):
    """Redirect stdout/stderr into the output buffer."""
    def write(self, text):
        if text:
            _log(text)
    def flush(self):
        pass


# ── Helpers ──────────────────────────────────────────────────────────

def _load_user_cats():
    if not os.path.isfile(CATEGORIES_FILE):
        return {}
    try:
        with open(CATEGORIES_FILE, "r") as f:
            return json.load(f)
    except (ValueError, IOError):
        return {}


def _save_user_cats(cats):
    with open(CATEGORIES_FILE, "w") as f:
        json.dump(cats, f, indent=2)


# ── API routes ───────────────────────────────────────────────────────

def _serialize_params(spec):
    """Serialize a param spec for the GUI. Preserves string min/max (param
    name references) so the client can display dynamic ranges."""
    if not spec:
        return None
    out = []
    for p in spec["params"]:
        out.append({
            "name":  p["name"],
            "type":  p.get("type", "int"),
            "width": p.get("width", ""),
            "min":   p["min"],
            "max":   p["max"],
            "range_text": format_param_range_text(p),
        })
    return out


@app.get("/api/tests")
def api_tests():
    cats = []
    for cat_name in CATEGORIES:
        tests = []
        for t in TEST_LIST:
            if t["category"] != cat_name:
                continue
            spec = TEST_PARAM_SPECS.get(t["id"])
            tests.append({
                "id": t["id"],
                "task_name": t["task_name"],
                "description": t["description"],
                "params": _serialize_params(spec),
                "task_display": spec["task_name"] if spec else t["task_name"],
            })
        cats.append({"name": cat_name, "tests": tests})
    return {"categories": cats, "total": len(TEST_LIST)}


@app.get("/api/user-cats")
def api_get_user_cats():
    return {"categories": _load_user_cats()}


@app.post("/api/user-cats")
def api_save_user_cat():
    data = request.json
    name = (data.get("name") or "").strip()
    ids = data.get("test_ids", [])
    if not name or not ids:
        response.status = 400
        return {"error": "name and test_ids required"}
    cats = _load_user_cats()
    cats[name] = ids
    _save_user_cats(cats)
    return {"ok": True}


@app.delete("/api/user-cats/<name>")
def api_delete_user_cat(name):
    cats = _load_user_cats()
    if name in cats:
        del cats[name]
        _save_user_cats(cats)
    return {"ok": True}


@app.post("/api/run")
def api_run():
    with _lock:
        if _state["running"]:
            response.status = 409
            return {"error": "A run is already in progress"}

    data = request.json
    test_ids = set(data.get("test_ids", []))
    selected = [t for t in TEST_LIST if t["id"] in test_ids]
    if not selected:
        response.status = 400
        return {"error": "No valid tests selected"}

    order = data.get("order", "default")
    rep = data.get("repeat", "1")
    log_type = data.get("log_type", "both")
    verbose = data.get("verbose", True)
    raw_params = data.get("params", {}) or {}
    param_overrides = {}
    for k, v in raw_params.items():
        try:
            param_overrides[int(k)] = v
        except (TypeError, ValueError):
            continue

    if order == "random":
        random.shuffle(selected)

    if str(rep).lower() == "endless":
        repeat = ENDLESS_LOOP_LIMIT
    else:
        try:
            repeat = max(1, int(rep))
        except (ValueError, TypeError):
            repeat = 1

    with _lock:
        _state["running"] = True
        _state["output"] = []

    t = threading.Thread(target=_run_worker,
                         args=(selected, repeat, log_type == "both", verbose,
                               param_overrides),
                         daemon=True)
    t.start()
    return {"ok": True, "count": len(selected)}


@app.get("/api/output")
def api_output():
    offset = int(request.query.get("offset", 0))
    with _lock:
        lines = _state["output"][offset:]
        return {"lines": lines, "offset": len(_state["output"]),
                "running": _state["running"]}


def _run_worker(selected, repeat, extended_log, verbose, param_overrides=None):
    old_out, old_err = sys.stdout, sys.stderr
    cap = _LogCapture()
    sys.stdout = cap
    sys.stderr = cap
    try:
        _log("[INFO] Tests to run ({}):\n".format(len(selected)))
        for t in selected:
            _log("  - Test {}: {} ({})\n".format(
                t["id"], t["task_name"], t["category"]))

        tb_path, fl_path, resolved_map = generate_tb_and_filelist(
            selected, param_overrides=param_overrides)

        ts = datetime.datetime.now().strftime("%d.%m.%Y_%H-%M-%S")
        run_info = {"test_ids": [t["id"] for t in selected],
                    "iterations": repeat}

        for i in range(repeat):
            if repeat > 1:
                _log("\n" + "=" * 60 + "\n")
                _log("  ITERATION {} of {}\n".format(i + 1, repeat))
                _log("=" * 60 + "\n")

            raw = compile_and_run(fl_path, verbose_stdout=verbose)
            if raw is None:
                _log("[ERROR] Simulation failed on iteration {}\n".format(i + 1))
                break

            results = parse_results(raw, selected,
                                    resolved_map=resolved_map,
                                    param_overrides=param_overrides)

            _log("\n[RESULTS]\n")
            pc = fc = uc = 0
            for tid, r in sorted(results.items()):
                s = r["status"]
                if s == "PASS":
                    pc += 1
                elif s == "FAIL":
                    fc += 1
                else:
                    uc += 1
                _log("  Test {:<3} [{}] {}\n".format(tid, s, r["name"]))
                if r.get("params_text"):
                    _log("           params: {}\n".format(r["params_text"]))

            _log("\n  TOTAL: {} PASSED | {} FAILED | {} UNKNOWN\n".format(
                pc, fc, uc))

            suf = "_{}".format(i + 1) if repeat > 1 else ""
            write_short_log(
                results,
                os.path.join(LOG_DIR, "short_log_{}{}.txt".format(ts, suf)),
                run_info)
            if extended_log:
                write_extended_log(
                    results, raw,
                    os.path.join(LOG_DIR, "extended_log_{}{}.txt".format(ts, suf)),
                    run_info)

        _log("\n[INFO] Done.\n")
    except Exception as e:
        _log("\n[ERROR] {}\n".format(e))
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        with _lock:
            _state["running"] = False


# ── HTML page ────────────────────────────────────────────────────────

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Test Runner</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
     background:#f0f2f5;color:#333;height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* ── Header ── */
.hdr{background:#2c3e50;color:#fff;padding:10px 20px;font-size:17px;font-weight:600;
     display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.hdr .sub{font-size:12px;opacity:.65;font-weight:400}

/* ── Content area ── */
.content{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden}

/* ── Main panels ── */
.main{flex:3;display:grid;grid-template-columns:3fr 2fr;gap:10px;padding:10px 10px 6px;
      min-height:0;overflow:hidden}
.panel{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);
       display:flex;flex-direction:column;overflow:hidden;min-height:0}
.ph{padding:10px 14px;border-bottom:1px solid #eaeaea;display:flex;align-items:center;gap:6px;flex-shrink:0}
.ph h2{font-size:13px;font-weight:700;margin-right:auto;color:#2c3e50}
.pb{flex:1;overflow-y:auto;padding:4px 0}

/* ── Buttons ── */
.btn{border:none;border-radius:4px;padding:5px 10px;font-size:11px;cursor:pointer;font-weight:600;transition:background .15s}
.b0{background:#e9ecef;color:#495057}.b0:hover{background:#dee2e6}
.bp{background:#3498db;color:#fff}.bp:hover{background:#2980b9}
.bd{background:#e74c3c;color:#fff}.bd:hover{background:#c0392b}
.btn-run{background:#27ae60;color:#fff;font-size:15px;font-weight:700;padding:11px;
         border-radius:6px;width:100%;margin:10px 0;cursor:pointer;border:none;transition:background .15s}
.btn-run:hover{background:#219a52}
.btn-run:disabled{background:#95a5a6;cursor:not-allowed}

/* ── Test list ── */
/* Visual hierarchy: categories > tests > params */
.ch{display:flex;align-items:center;padding:9px 14px 4px;cursor:pointer;user-select:none;
    border-top:1px solid #e8eaed;margin-top:2px}
.ch:first-child{border-top:none;margin-top:0}
.ch:hover{background:#f8f9fa}
.ch input{margin-right:8px;cursor:pointer}
.ch label{font-weight:700;font-size:14px;color:#1a2a3a;cursor:pointer;letter-spacing:.2px}
.ch .cnt{margin-left:6px;font-size:11px;color:#8a96a3;font-weight:500}
.ti{display:flex;align-items:center;padding:3px 14px 3px 40px}
.ti:hover{background:#f8f9fa}
.ti input{margin-right:7px;cursor:pointer}
.ti label{font-size:12.5px;color:#445566;cursor:pointer}
.ti .tn{font-weight:700;color:#2c3e50;min-width:56px;display:inline-block}
.ti .arr{margin-left:8px;color:#7f8fa0;font-size:10px;cursor:pointer;
         padding:1px 5px;border-radius:3px;user-select:none;
         transition:transform .15s,background .15s,color .15s}
.ti .arr:hover{background:#e3edf7;color:#2c3e50}
.ti .arr.open{transform:rotate(90deg);color:#2c3e50}

/* ── Per-test params (collapsible) ── */
.tp{display:none;padding:4px 14px 8px 58px;font-size:10.5px;color:#37474f;
    background:#eaf2fb;border-left:3px solid #3498db;margin:2px 0 6px 22px;
    border-radius:0 4px 4px 0}
.tp.open{display:block}
.tp .pr{display:flex;align-items:center;gap:8px;margin:2px 0;padding:2px 6px;
        border-radius:4px;flex-wrap:wrap;transition:background .15s,box-shadow .15s}
.tp .pr.manual{background:#fffbe9;box-shadow:inset 0 0 0 1px #ead8a0}
.tp .pn{font-weight:700;color:#1a3a5b;min-width:120px;font-size:11px}
.tp .pr.manual .pn{color:#8d7030}
.tp .ptype{color:#5c7891;font-size:10px;font-style:italic;min-width:60px}
.tp .rng{color:#6b7a89;font-size:10px;min-width:120px}
.tp .rng.dyn{color:#b88a3a}
.tp label{cursor:pointer;color:#37474f;font-size:10.5px}
.tp input[type=number]{min-width:90px;padding:2px 5px;border:1px solid #b8c8d8;
                       border-radius:3px;font-size:10.5px;background:#fff;
                       transition:border-color .15s,background-color .15s}
.tp input[type=number]:disabled{background:#e3e8ee;color:#a3adb6;border-color:#d0d7de}
.tp .pr.manual input[type=number]{border-color:#d6be7a;background:#fffef6}
.tp input[type=number].rand-val{background:#eef7ee;color:#2e6b3d;border-color:#a9ccb0;
                                font-weight:700}
.tp input[type=number].err{border-color:#e74c3c!important;background:#fff1f0!important;
                           box-shadow:0 0 0 2px rgba(231,76,60,.15)}
.tp .reroll{border:1px solid #b8c8d8;background:#fff;color:#2c3e50;border-radius:3px;
            font-size:11px;padding:1px 6px;cursor:pointer;line-height:1}
.tp .reroll:hover{background:#eaf2fb;border-color:#8fb3d4}
.tp .err-msg{color:#c0392b;font-size:10px;font-weight:600;margin-left:4px;
             min-width:0;flex-basis:100%;padding-left:130px}
.tp .err-msg:empty{display:none}

/* Shake animation for invalid manual input */
@keyframes shake-x{
  0%,100%{transform:translateX(0)}
  15%{transform:translateX(-5px)}
  30%{transform:translateX(5px)}
  45%{transform:translateX(-4px)}
  60%{transform:translateX(4px)}
  75%{transform:translateX(-2px)}
  90%{transform:translateX(2px)}
}
.tp input[type=number].shake{animation:shake-x .42s cubic-bezier(.36,.07,.19,.97) both}

/* ── Settings ── */
.ss{padding:10px 14px;border-bottom:1px solid #f0f0f0}
.ss h3{font-size:12px;font-weight:700;margin-bottom:8px;color:#2c3e50}
.fr{display:flex;align-items:center;margin-bottom:7px;font-size:11.5px}
.fr>label:first-child{width:62px;color:#777;flex-shrink:0}
.fr select,.fr input[type=text]{padding:3px 6px;border:1px solid #ddd;border-radius:3px;font-size:11.5px}
.rg label{margin-right:10px;color:#555;font-size:11.5px}
.sc{text-align:center;font-size:12px;color:#888;padding:2px 0 6px}

/* ── User categories ── */
.cl{flex:1;overflow-y:auto;border:1px solid #eee;border-radius:4px;margin-top:6px;min-height:40px}
.ci{padding:5px 10px;font-size:11px;cursor:pointer;border-bottom:1px solid #f5f5f5;font-family:Consolas,"Courier New",monospace}
.ci:hover{background:#f0f7ff}
.ci.sel{background:#e3f2fd;font-weight:600}

/* ── Output ── */
.out{flex:2;display:flex;flex-direction:column;margin:0 10px 6px;
     background:#1e1e1e;border-radius:8px;min-height:0;overflow:hidden;
     box-shadow:0 1px 4px rgba(0,0,0,.15)}
.oh{padding:7px 14px;display:flex;align-items:center;border-bottom:1px solid #333;flex-shrink:0}
.oh h2{color:#888;font-size:11px;font-weight:500;margin-right:auto;text-transform:uppercase;letter-spacing:.5px}
.ob{flex:1;overflow-y:auto;padding:6px 14px;
    font-family:"Cascadia Code","Fira Code","Source Code Pro",Consolas,monospace;
    font-size:11.5px;line-height:1.55;color:#d4d4d4;white-space:pre-wrap;word-break:break-word}
.ob .p{color:#4ec9b0}.ob .f{color:#f44747;font-weight:700}.ob .i{color:#569cd6}

/* ── Status bar ── */
.sb{padding:5px 18px;font-size:11px;color:#777;border-top:1px solid #e0e0e0;background:#fafafa;flex-shrink:0}
</style>
</head>
<body>

<div class="hdr">
  <span>&#9654; Test Runner</span>
  <span class="sub" id="hi">loading...</span>
</div>

<div class="content">
<div class="main">

  <!-- ── Left: test selection ── -->
  <div class="panel">
    <div class="ph">
      <h2>Test Selection</h2>
      <button class="btn b0" onclick="selAll()">Select All</button>
      <button class="btn b0" onclick="selNone()">Deselect All</button>
    </div>
    <div class="pb" id="tl"></div>
  </div>

  <!-- ── Right: settings + categories ── -->
  <div class="panel" style="overflow-y:auto">
    <div class="ss">
      <h3>Run Settings</h3>
      <div class="fr">
        <label>Order:</label>
        <select id="sOrd"><option value="default">Default</option><option value="random">Random</option></select>
      </div>
      <div class="fr">
        <label>Repeat:</label>
        <input type="text" id="sRep" value="1" style="width:75px" placeholder="1 or endless">
      </div>
      <div class="fr">
        <label>Log type:</label>
        <span class="rg">
          <label><input type="radio" name="lt" value="short"> Short only</label>
          <label><input type="radio" name="lt" value="both" checked> Both</label>
        </span>
      </div>
      <div class="fr">
        <label></label>
        <label><input type="checkbox" id="sVb" checked> Show sim output</label>
      </div>
    </div>

    <div style="padding:0 14px">
      <button class="btn-run" id="rb" onclick="doRun()">&#9654;  RUN TESTS</button>
      <div class="sc" id="sc">0 tests selected</div>
    </div>

    <div class="ss" style="flex:1;display:flex;flex-direction:column">
      <h3>User Categories</h3>
      <div style="display:flex;gap:4px;margin-bottom:4px">
        <button class="btn bp" onclick="ucSave()">Save Selection...</button>
        <button class="btn b0" onclick="ucLoad()">Load</button>
        <button class="btn bd" onclick="ucDel()">Delete</button>
      </div>
      <div class="cl" id="ucl"></div>
    </div>
  </div>

</div><!-- .main -->

<!-- ── Output ── -->
<div class="out">
  <div class="oh">
    <h2>Output</h2>
    <button class="btn b0" onclick="clrOut()" style="font-size:10px;padding:2px 7px">Clear</button>
  </div>
  <div class="ob" id="ob"></div>
</div>

</div><!-- .content -->

<div class="sb" id="sb">Loading...</div>

<script>
var D=[];var ucSel=null;var pt=null;var po=0;

/* ── Per-parameter state ──
   pState[tid][pname] = {mode:'random'|'manual', randomValue:int|null, manualValue:string}
   Random values are rolled eagerly as soon as the user can see them, so the
   *actual* values that will be used in the run are always visible in the UI
   and referenced-parameter validation works correctly (e.g. number_of_cycles
   can be validated against the real partial_address roll, not against its
   spec-min fallback). */
var pState={};

/* ── Init ── */
function init(){
  fetch("/api/tests").then(function(r){return r.json()}).then(function(d){
    D=d.categories;
    $("hi").textContent=d.total+" tests available";
    $("sb").textContent="Ready | "+d.total+" tests available";
    render();ucRefresh();
  });
}
function $(id){return document.getElementById(id)}

/* ── Render tests ── */
function render(){
  var c=$("tl");c.innerHTML="";
  D.forEach(function(cat,ci){
    var h=document.createElement("div");h.className="ch";
    h.innerHTML='<input type="checkbox" id="c'+ci+'" onchange="tgCat('+ci+')">'+
      '<label for="c'+ci+'">'+esc(cat.name)+'</label><span class="cnt">('+cat.tests.length+')</span>';
    c.appendChild(h);
    cat.tests.forEach(function(t){
      var d=document.createElement("div");d.className="ti";
      var hasParams=(t.params&&t.params.length);
      var arrHtml=hasParams?'<span class="arr" id="arr_t'+t.id+'" title="Show parameters" onclick="togglePW(event,'+t.id+')">&#9654;</span>':'';
      d.innerHTML='<input type="checkbox" id="t'+t.id+'" data-c="'+ci+'" onchange="upCat('+ci+');upCnt()">'+
        '<label for="t'+t.id+'"><span class="tn">Test '+t.id+'</span> '+esc(t.task_name)+'</label>'+
        arrHtml;
      c.appendChild(d);
      if(t.params&&t.params.length){
        initParamState(t.id,t.params);
        var pw=document.createElement("div");pw.className="tp";
        pw.id="pw_t"+t.id;
        t.params.forEach(function(p){
          var gn="m_t"+t.id+"_"+p.name;
          var vid="v_t"+t.id+"_"+p.name;
          var typeTxt=p.type+(p.width?" "+p.width:"");
          var row=document.createElement("div");row.className="pr";
          row.id="row_t"+t.id+"_"+p.name;
          row.setAttribute("data-tid",t.id);
          row.setAttribute("data-pname",p.name);
          row.innerHTML='<span class="pn">'+esc(p.name)+'</span>'+
            '<span class="ptype">'+esc(typeTxt)+'</span>'+
            '<span class="rng" id="rng_t'+t.id+'_'+p.name+'">'+esc(p.range_text)+'</span>'+
            '<label><input type="radio" name="'+gn+'" value="random" checked onchange="onParMode('+t.id+',\''+p.name+'\',false)"> Random</label>'+
            '<label><input type="radio" name="'+gn+'" value="manual" onchange="onParMode('+t.id+',\''+p.name+'\',true)"> Manual</label>'+
            '<input type="number" id="'+vid+'" placeholder="'+esc(p.range_text)+'" '+
            'style="width:110px" '+
            'data-tid="'+t.id+'" data-pname="'+p.name+'" '+
            'oninput="onManInput(this,'+t.id+',\''+p.name+'\')" '+
            'onblur="onManBlur(this,'+t.id+',\''+p.name+'\')" '+
            'onkeydown="onManKey(event,this,'+t.id+',\''+p.name+'\')" disabled>'+
            '<button type="button" class="reroll" id="rr_t'+t.id+'_'+p.name+'" '+
            'title="Re-roll random value" onclick="rerollParam('+t.id+',\''+p.name+'\')">&#x21bb; re-roll</button>'+
            '<span class="err-msg" id="err_t'+t.id+'_'+p.name+'"></span>';
          pw.appendChild(row);
        });
        c.appendChild(pw);
        refreshTestRows(t.id);
      }
    });
  });
  upCnt();
}
function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML}

/* ── Selection ── */
function selAll(){qa("#tl input[type=checkbox]",function(c){c.checked=true});upCnt()}
function selNone(){qa("#tl input[type=checkbox]",function(c){c.checked=false});upCnt()}
function tgCat(ci){var v=$("c"+ci).checked;qa('[data-c="'+ci+'"]',function(c){c.checked=v});upCnt()}
function upCat(ci){var a=true;qa('[data-c="'+ci+'"]',function(c){if(!c.checked)a=false});$("c"+ci).checked=a}
function ids(){var r=[];D.forEach(function(cat){cat.tests.forEach(function(t){var c=$("t"+t.id);if(c&&c.checked)r.push(t.id)})});return r}
function upCnt(){var n=ids().length;$("sc").textContent=n+" test"+(n!==1?"s":"")+" selected"}
function qa(s,fn){document.querySelectorAll(s).forEach(fn)}

/* ── Expand / collapse the params panel for a single test ── */
function togglePW(ev,tid){
  if(ev){ev.stopPropagation();ev.preventDefault();}
  var pw=$("pw_t"+tid);
  var arr=$("arr_t"+tid);
  if(!pw) return;
  var open=pw.classList.toggle("open");
  if(arr){
    if(open){arr.classList.add("open");arr.title="Hide parameters";}
    else   {arr.classList.remove("open");arr.title="Show parameters";}
  }
}
function openPW(tid){
  var pw=$("pw_t"+tid);
  var arr=$("arr_t"+tid);
  if(pw&&!pw.classList.contains("open")){
    pw.classList.add("open");
    if(arr){arr.classList.add("open");arr.title="Hide parameters";}
  }
}

/* ── Helpers for param-spec lookup ── */
function _paramSpec(tid,pname){
  for(var ci=0;ci<D.length;ci++){
    var cat=D[ci];
    for(var ti=0;ti<cat.tests.length;ti++){
      var t=cat.tests[ti];
      if(t.id!==tid||!t.params) continue;
      for(var i=0;i<t.params.length;i++){
        if(t.params[i].name===pname) return {test:t,param:t.params[i]};
      }
    }
  }
  return null;
}
function _params(tid){
  for(var ci=0;ci<D.length;ci++){
    var cat=D[ci];
    for(var ti=0;ti<cat.tests.length;ti++){
      if(cat.tests[ti].id===tid) return cat.tests[ti].params||[];
    }
  }
  return [];
}

/* Resolve a min/max for a specific param, walking any chain of string refs
   and using the live pState (manual input or pre-rolled random value). */
function _resolveBound(tid,bound,which){
  if(typeof bound==="number") return {val:bound,dyn:false};
  var info=_paramSpec(tid,bound);
  if(!info) return {val:0,dyn:true,label:bound};
  var st=pState[tid]&&pState[tid][bound];
  if(st){
    if(st.mode==="manual"){
      if(st.manualValue!==""){
        var v=parseInt(st.manualValue,10);
        if(!isNaN(v)) return {val:v,dyn:true,label:bound,known:true};
      }
      return {val:null,dyn:true,label:bound,known:false};
    }
    if(st.randomValue!==null&&st.randomValue!==undefined){
      return {val:st.randomValue,dyn:true,label:bound,known:true};
    }
  }
  /* fallback: walk spec chain */
  var inner=info.param[which];
  return _resolveBound(tid,inner,which);
}

function _rangeForParam(tid,pname){
  var info=_paramSpec(tid,pname); if(!info) return null;
  var p=info.param;
  var lo=_resolveBound(tid,p.min,"min");
  var hi=_resolveBound(tid,p.max,"max");
  return {lo:lo,hi:hi,spec:p};
}

function _rangeText(r){
  var loTxt=(r.lo.dyn)?(r.lo.known===false?r.lo.label:String(r.lo.val)):String(r.lo.val);
  var hiTxt=(r.hi.dyn)?(r.hi.known===false?r.hi.label:String(r.hi.val)):String(r.hi.val);
  return "["+loTxt+".."+hiTxt+"]";
}
function _rangeIsDyn(r){
  return (r.lo.dyn&&r.lo.known===false)||(r.hi.dyn&&r.hi.known===false);
}
function _randInt(lo,hi){return lo+Math.floor(Math.random()*(hi-lo+1))}

/* ── Param-state lifecycle ── */
function initParamState(tid,params){
  if(pState[tid]) return;
  pState[tid]={};
  for(var i=0;i<params.length;i++){
    pState[tid][params[i].name]={mode:"random",randomValue:null,manualValue:""};
  }
  rollRandomsForTest(tid,true);
}

/* Walk params in declared order; for each random param whose randomValue is
   either unset or now outside the effective range, roll a fresh value.
   forceAll=true forces a re-roll for every random param (used on init and
   when the user clicks re-roll on a param — dependents are refreshed only
   if their current value goes out of range). */
function rollRandomsForTest(tid,forceAll){
  var params=_params(tid);
  for(var i=0;i<params.length;i++){
    var p=params[i];
    var st=pState[tid][p.name];
    if(st.mode!=="random") continue;
    var r=_rangeForParam(tid,p.name);
    if(!r||r.lo.known===false||r.hi.known===false) continue;
    if(r.lo.val>r.hi.val){st.randomValue=null;continue}
    var cur=st.randomValue;
    if(forceAll||cur===null||cur===undefined||cur<r.lo.val||cur>r.hi.val){
      st.randomValue=_randInt(r.lo.val,r.hi.val);
    }
  }
}

function refreshTestRows(tid){
  var params=_params(tid);
  for(var i=0;i<params.length;i++){
    refreshRow(tid,params[i].name);
  }
}

function refreshRow(tid,pname){
  var st=pState[tid]&&pState[tid][pname]; if(!st) return;
  var r=_rangeForParam(tid,pname);
  var rngEl=$("rng_t"+tid+"_"+pname);
  if(rngEl){
    rngEl.textContent=_rangeText(r);
    if(_rangeIsDyn(r)) rngEl.classList.add("dyn"); else rngEl.classList.remove("dyn");
  }
  var inp=$("v_t"+tid+"_"+pname);
  var rr=$("rr_t"+tid+"_"+pname);
  var row=$("row_t"+tid+"_"+pname);
  if(!inp) return;
  if(st.mode==="manual"){
    inp.disabled=false;
    inp.classList.remove("rand-val");
    if(row) row.classList.add("manual");
    if(rr) rr.style.display="none";
    if(inp.value!==st.manualValue) inp.value=st.manualValue;
    validateManual(tid,pname,false);
  } else {
    inp.disabled=true;
    inp.classList.add("rand-val");
    inp.classList.remove("err");
    if(row) row.classList.remove("manual");
    if(rr) rr.style.display="";
    inp.value=(st.randomValue!==null&&st.randomValue!==undefined)?String(st.randomValue):"";
    clearParamError(tid,pname);
  }
}

function clearParamError(tid,pname){
  var err=$("err_t"+tid+"_"+pname);
  var inp=$("v_t"+tid+"_"+pname);
  if(err) err.textContent="";
  if(inp) inp.classList.remove("err");
}

function shakeAndShowErr(tid,pname,msg){
  var err=$("err_t"+tid+"_"+pname);
  var inp=$("v_t"+tid+"_"+pname);
  if(err) err.textContent=msg;
  if(inp){
    inp.classList.add("err");
    inp.classList.remove("shake");
    void inp.offsetWidth; /* force reflow to restart animation */
    inp.classList.add("shake");
    setTimeout(function(){if(inp)inp.classList.remove("shake")},500);
  }
}

/* Validate a manual param against its current effective range. When the
   value is invalid and `commit` is true we show a shake + inline message;
   while the user is still typing we only clear a prior error. Returns
   true when the stored manualValue is empty or valid. */
function validateManual(tid,pname,commit){
  var st=pState[tid][pname];
  if(st.mode!=="manual") return true;
  var raw=st.manualValue;
  if(raw==="") { clearParamError(tid,pname); return true; }
  if(!commit&&(raw==="-"||raw==="+")) return true;
  var v=parseInt(raw,10);
  if(isNaN(v)){
    if(commit) shakeAndShowErr(tid,pname,"must be an integer -- try again");
    return false;
  }
  var r=_rangeForParam(tid,pname);
  if(r&&r.lo.known!==false&&r.hi.known!==false){
    if(v<r.lo.val||v>r.hi.val){
      shakeAndShowErr(tid,pname,
        "must be in ["+r.lo.val+".."+r.hi.val+"] -- try again or pick Random");
      return false;
    }
  }
  clearParamError(tid,pname);
  return true;
}

/* Re-validate all manual rows on a test (bounds may have shifted because
   another param changed). */
function revalidateManuals(tid){
  var params=_params(tid);
  for(var i=0;i<params.length;i++){
    var st=pState[tid][params[i].name];
    if(st&&st.mode==="manual") validateManual(tid,params[i].name,true);
  }
}

/* ── Event handlers ── */
function onParMode(tid,pname,manual){
  var st=pState[tid][pname];
  st.mode=manual?"manual":"random";
  if(!manual){
    /* switching to random -> roll fresh value for this one */
    st.randomValue=null;
  } else {
    /* switching to manual -> start with empty field for the user */
    st.manualValue="";
  }
  rollRandomsForTest(tid,false);
  refreshTestRows(tid);
  revalidateManuals(tid);
  if(manual){var e=$("v_t"+tid+"_"+pname); if(e) e.focus();}
}

function rerollParam(tid,pname){
  var st=pState[tid][pname];
  if(!st||st.mode!=="random") return;
  var r=_rangeForParam(tid,pname);
  if(r&&r.lo.known!==false&&r.hi.known!==false&&r.lo.val<=r.hi.val){
    st.randomValue=_randInt(r.lo.val,r.hi.val);
  }
  rollRandomsForTest(tid,false);
  refreshTestRows(tid);
  revalidateManuals(tid);
}

function onManInput(inp,tid,pname){
  var st=pState[tid][pname];
  st.manualValue=inp.value;
  /* update dependents' visible range + re-roll randoms whose value is now
     out of range; also clear any stale error as the user types */
  rollRandomsForTest(tid,false);
  var params=_params(tid);
  for(var i=0;i<params.length;i++){
    if(params[i].name!==pname) refreshRow(tid,params[i].name);
    else {
      /* refresh own range text but do not overwrite the in-progress input */
      var r=_rangeForParam(tid,pname);
      var rngEl=$("rng_t"+tid+"_"+pname);
      if(rngEl){
        rngEl.textContent=_rangeText(r);
        if(_rangeIsDyn(r)) rngEl.classList.add("dyn"); else rngEl.classList.remove("dyn");
      }
    }
  }
  validateManual(tid,pname,false);
  revalidateManuals(tid);
}

function onManBlur(inp,tid,pname){
  pState[tid][pname].manualValue=inp.value;
  validateManual(tid,pname,true);
}

function onManKey(ev,inp,tid,pname){
  if(ev.key==="Enter"){
    pState[tid][pname].manualValue=inp.value;
    var ok=validateManual(tid,pname,true);
    if(!ok) ev.preventDefault();
  }
}

/* ── Collect per-test params (Manual or Random, always with a concrete
     value). Returns {ok:true, params:{...}} or {ok:false, error:"..."} ── */
function collectParams(){
  var out={};
  for(var ci=0;ci<D.length;ci++){
    var cat=D[ci];
    for(var ti=0;ti<cat.tests.length;ti++){
      var t=cat.tests[ti];
      if(!t.params||!t.params.length) continue;
      var cb=$("t"+t.id); if(!cb||!cb.checked) continue;
      var pobj={};
      var st=pState[t.id]||{};
      /* make sure all random values are up to date before collecting */
      rollRandomsForTest(t.id,false);
      for(var i=0;i<t.params.length;i++){
        var p=t.params[i];
        var ps=st[p.name];
        if(!ps){
          openPW(t.id);
          return {ok:false,error:"Internal: missing state for test "+t.id+" param '"+p.name+"'."};
        }
        if(ps.mode==="manual"){
          if(ps.manualValue===""||ps.manualValue==null){
            openPW(t.id);
            shakeAndShowErr(t.id,p.name,"enter a value or pick Random");
            return {ok:false,error:"Test "+t.id+": enter a value for '"+p.name+"' or pick Random."};
          }
          var v=parseInt(ps.manualValue,10);
          if(isNaN(v)){
            openPW(t.id);
            shakeAndShowErr(t.id,p.name,"must be an integer");
            return {ok:false,error:"Test "+t.id+": '"+p.name+"' must be an integer."};
          }
          var r=_rangeForParam(t.id,p.name);
          if(r&&r.lo.known!==false&&r.hi.known!==false){
            if(v<r.lo.val||v>r.hi.val){
              openPW(t.id);
              shakeAndShowErr(t.id,p.name,
                "must be in ["+r.lo.val+".."+r.hi.val+"] -- try again");
              return {ok:false,error:"Test "+t.id+": '"+p.name+
                "' must be in ["+r.lo.val+".."+r.hi.val+"]."};
            }
          }
          pobj[p.name]={mode:"manual",value:v};
        } else {
          if(ps.randomValue===null||ps.randomValue===undefined){
            openPW(t.id);
            return {ok:false,error:"Test "+t.id+": could not roll random value for '"+p.name+"'."};
          }
          pobj[p.name]={mode:"random",value:ps.randomValue};
        }
      }
      out[t.id]=pobj;
    }
  }
  return {ok:true,params:out};
}

/* ── User categories ── */
function ucRefresh(){
  fetch("/api/user-cats").then(function(r){return r.json()}).then(function(d){
    var l=$("ucl");l.innerHTML="";ucSel=null;
    Object.keys(d.categories).sort().forEach(function(n){
      var ids=d.categories[n].slice().sort(function(a,b){return a-b});
      var e=document.createElement("div");e.className="ci";
      e.textContent=n+"  ("+ids.length+" tests: "+ids.join(", ")+")";
      e.onclick=function(){qa(".ci",function(x){x.classList.remove("sel")});e.classList.add("sel");ucSel=n};
      e.ondblclick=function(){ucSel=n;ucLoad()};
      l.appendChild(e);
    });
  });
}
function ucSave(){
  var s=ids();if(!s.length){alert("Select some tests first.");return}
  var n=prompt("Category name:");if(!n||!n.trim())return;
  fetch("/api/user-cats",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:n.trim(),test_ids:s})}).then(function(){ucRefresh()});
}
function ucLoad(){
  if(!ucSel){alert("Select a category first.");return}
  fetch("/api/user-cats").then(function(r){return r.json()}).then(function(d){
    var t=new Set(d.categories[ucSel]||[]);
    selNone();
    D.forEach(function(cat,ci){cat.tests.forEach(function(tt){var c=$("t"+tt.id);if(c)c.checked=t.has(tt.id)});upCat(ci)});
    upCnt();
  });
}
function ucDel(){
  if(!ucSel){alert("Select a category first.");return}
  if(!confirm('Delete "'+ucSel+'"?'))return;
  fetch("/api/user-cats/"+encodeURIComponent(ucSel),{method:"DELETE"}).then(function(){ucRefresh()});
}

/* ── Output ── */
function aOut(txt,cls){
  var o=$("ob");
  if(cls){var s=document.createElement("span");s.className=cls;s.textContent=txt;o.appendChild(s)}
  else{o.appendChild(document.createTextNode(txt))}
  o.scrollTop=o.scrollHeight;
}
function clrOut(){$("ob").innerHTML=""}

/* ── Run ── */
function doRun(){
  var s=ids();if(!s.length){alert("Select at least one test.");return}
  var pr=collectParams();
  if(!pr.ok){alert(pr.error);return}
  var lt=document.querySelector('input[name=lt]:checked').value;
  clrOut();
  $("rb").disabled=true;$("rb").textContent="\u23F3  RUNNING...";
  $("sb").textContent="Running... ("+s.length+" tests)";
  fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({test_ids:s,order:$("sOrd").value,repeat:$("sRep").value,
      log_type:lt,verbose:$("sVb").checked,params:pr.params})
  }).then(function(r){
    if(!r.ok)return r.json().then(function(e){alert(e.error||"Failed");rstBtn()});
    po=0;pt=setInterval(poll,400);
  }).catch(function(e){alert("Error: "+e);rstBtn()});
}
function poll(){
  fetch("/api/output?offset="+po).then(function(r){return r.json()}).then(function(d){
    d.lines.forEach(function(chunk){
      if(chunk.indexOf("PASS")!==-1)aOut(chunk,"p");
      else if(chunk.indexOf("FAIL")!==-1||chunk.indexOf("[ERROR]")!==-1)aOut(chunk,"f");
      else if(chunk.indexOf("[INFO]")!==-1||chunk.indexOf("[LOG]")!==-1||chunk.indexOf("[CMD]")!==-1)aOut(chunk,"i");
      else aOut(chunk);
    });
    po=d.offset;
    if(!d.running){clearInterval(pt);pt=null;rstBtn();
      var tot=D.reduce(function(s,c){return s+c.tests.length},0);
      $("sb").textContent="Done | "+tot+" tests available";}
  }).catch(function(){});
}
function rstBtn(){$("rb").disabled=false;$("rb").textContent="\u25B6  RUN TESTS"}

init();
</script>
</body>
</html>"""


@app.get("/")
def index():
    response.content_type = "text/html; charset=utf-8"
    return PAGE


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import socket

    start_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    port = start_port
    for attempt in range(20):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            break
        except OSError:
            s.close()
            port += 1
    else:
        print("[ERROR] Could not find a free port ({}-{})".format(
            start_port, start_port + 19))
        sys.exit(1)

    print("")
    print("=" * 50)
    print("  Test Runner GUI")
    print("  Open in browser: http://localhost:{}".format(port))
    print("=" * 50)
    print("")
    bottle_run(app, host="127.0.0.1", port=port, quiet=False, reloader=False)
