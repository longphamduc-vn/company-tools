"""Read-only probe of the real Outlook COM API for outlook-rule-manager.

SAFETY: this script never calls Rules.Save(). Outlook only persists rule changes
on Save(), so the temporary probe rule created in memory is discarded. The script
also never writes rules.yaml.

Usage (on a machine with Outlook Classic running):
    pip install pywin32 pyyaml
    cd outlook-rule-manager
    python tools/outlook_probe.py [path/to/rules.yaml]

Paste the full output back for review. Output contains rule and store names,
but not email addresses.
"""
import os
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import win32com.client  # noqa: E402

from core.models import MANAGED_PREFIX  # noqa: E402
from core.outlook_client import (  # noqa: E402
    OL_CONDITION_FROM,
    OL_CONDITION_SENDER_ADDRESS,
    OL_CONDITION_SUBJECT,
    WindowsOutlookClient,
)
from core.yaml_manager import YamlConfigManager  # noqa: E402

PROBE_NAME = f"{MANAGED_PREFIX}__probe_do_not_keep__"
results = []


def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((status, label))
    print(f"[{status}] {label}" + (f" -> {detail}" if detail else ""))


def info(label, detail=""):
    print(f"[INFO] {label}" + (f": {detail}" if detail else ""))


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "config", "rules.yaml")
    yaml_mgr = YamlConfigManager(config_path)  # load only, never saved here

    app = win32com.client.Dispatch("Outlook.Application")
    namespace = app.GetNamespace("MAPI")
    client = WindowsOutlookClient(namespace=namespace)

    # 1. Stores
    print("\n== 1. Stores ==")
    for s in client.get_stores():
        info("store", f"name='{s['name']}' path='{s['file_path']}' data_file={s['is_data_file']}")
    active = yaml_mgr.stores.get("active_archive")
    active_path = active.file_path if active else ""
    info("rules.yaml active_archive.file_path", active_path)
    check("active_archive matches a mounted store exactly", client.store_exists(active_path),
          "fix config/rules.yaml file_path to one of the paths above" if not client.store_exists(active_path) else "")

    # 2. Existing rules (read-only)
    print("\n== 2. Existing Outlook rules ==")
    rules_col = namespace.DefaultStore.GetRules()
    names = [r.Name for r in rules_col]
    info("rule count", str(len(names)))
    info("managed ([Companion]) rules", str(sum(n.startswith(MANAGED_PREFIX) for n in names)))
    dupes = [n for n, c in Counter(names).items() if c > 1]
    check("no duplicate rule names", not dupes, f"duplicates: {dupes}" if dupes else "")

    seen_types = Counter()
    for r in rules_col:
        try:
            conds = r.Conditions
            for i in range(1, conds.Count + 1):
                c = conds.Item(i)
                if c.Enabled:
                    seen_types[c.ConditionType] += 1
        except Exception as ex:
            check(f"read conditions of rule '{r.Name}'", False, str(ex))
    info("enabled ConditionType counts across rules", dict(seen_types))

    native = client.get_native_rules()
    check("get_native_rules runs", len(native) == len(names), f"{len(native)} parsed / {len(names)} rules")
    for n in native:
        flags = []
        if n.get("has_unsupported_conditions"):
            flags.append("unsupported")
        if n.get("unresolved_recipients"):
            flags.append(f"{len(n['unresolved_recipients'])} unresolved")
        info(f"rule '{n['name']}'",
             f"enabled={n['enabled']} emails={len(n['emails'])} domains={len(n['domains'])} "
             f"keywords={len(n['subject_keywords'])} {' '.join(flags)}")

    # 3. In-memory probe rule (NOT saved)
    print("\n== 3. In-memory probe (no Save) ==")
    probe_rules = namespace.DefaultStore.GetRules()
    rule = probe_rules.Create(PROBE_NAME, 0)
    try:
        conds = rule.Conditions
        check("ConditionType From == 1", conds.From.ConditionType == OL_CONDITION_FROM, str(conds.From.ConditionType))
        check("ConditionType Subject == 2", conds.Subject.ConditionType == OL_CONDITION_SUBJECT, str(conds.Subject.ConditionType))
        check("ConditionType SenderAddress == 17", conds.SenderAddress.ConditionType == OL_CONDITION_SENDER_ADDRESS,
              str(conds.SenderAddress.ConditionType))

        for label, cond, attr, value in [
            ("SenderAddress.Address", conds.SenderAddress, "Address", ["@example.com", "@example.org"]),
            ("Subject.Text", conds.Subject, "Text", ["probe-keyword"]),
        ]:
            try:
                setattr(cond, attr, value)
                cond.Enabled = True
                got = list(getattr(cond, attr) or [])
                check(f"assign list to {label}", got == value, f"read back {got}")
            except Exception as ex:
                check(f"assign list to {label}", False, str(ex))
            try:
                cond.Enabled = False
                setattr(cond, attr, [])
                check(f"assign [] to {label}", True)
            except Exception as ex:
                # Tolerated by the app (wrapped in try/except); informative only.
                info(f"assign [] to {label} raised (tolerated by app)", str(ex))

        try:
            conds.From.Recipients.Add("probe@example.com")
            conds.From.Enabled = True
            resolved = conds.From.Recipients.ResolveAll()
            info("From.Recipients.ResolveAll() for external SMTP", str(resolved))
            while conds.From.Recipients.Count > 0:
                conds.From.Recipients.Remove(1)
            check("From recipients add/remove", conds.From.Recipients.Count == 0)
        except Exception as ex:
            check("From recipients add/remove", False, str(ex))

        try:
            rule.Actions.Stop.Enabled = True
            check("Actions.Stop.Enabled settable", bool(rule.Actions.Stop.Enabled))
        except Exception as ex:
            check("Actions.Stop.Enabled settable", False, str(ex))

        try:
            rule.ExecutionOrder = probe_rules.Count
            check("ExecutionOrder settable", rule.ExecutionOrder == probe_rules.Count, str(rule.ExecutionOrder))
        except Exception as ex:
            check("ExecutionOrder settable", False, str(ex))
    finally:
        try:
            probe_rules.Remove(PROBE_NAME)
            check("Rules.Remove(name) works", True)
        except Exception as ex:
            check("Rules.Remove(name) works", False, str(ex))

    fresh = [r.Name for r in namespace.DefaultStore.GetRules()]
    check("probe rule was NOT persisted", PROBE_NAME not in fresh)

    print("\n== Summary ==")
    fails = [label for status, label in results if status == "FAIL"]
    print(f"{len(results) - len(fails)} passed, {len(fails)} failed")
    for label in fails:
        print(f"  FAIL: {label}")


if __name__ == "__main__":
    main()
