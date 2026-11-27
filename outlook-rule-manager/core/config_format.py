"""v3 'folders:' configuration format: parser, serializer, and v2 -> v3 migrator."""
import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import yaml

from core.models import RuleConfig, StoreConfig, rule_name_from_folder


class IndentedDumper(yaml.SafeDumper):
    """YAML Dumper that indents nested list items under their parent key."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def dump_yaml(data: Dict[str, Any]) -> str:
    """Serialize a v3 config dict to YAML text."""
    return yaml.dump(
        data,
        Dumper=IndentedDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def normalize_domain(domain_str: str) -> str:
    """Normalize a domain to lowercase stripped '@domain' format; return '' if empty."""
    val = (domain_str or "").lower().strip()
    if not val:
        return ""
    if "@" in val:
        val = val.split("@", 1)[1].strip()
    val = val.lstrip("@").strip()
    if not val:
        return ""
    return f"@{val}"


def normalize_domains(domains: Iterable[str]) -> List[str]:
    """Normalize a list of domains and drop empty entries."""
    return [d for d in (normalize_domain(x) for x in (domains or [])) if d]


def normalize_keywords(keywords: Iterable[str]) -> List[str]:
    """Strip whitespace, drop empty items, and deduplicate case-insensitively keeping first spelling."""
    seen: Set[str] = set()
    result: List[str] = []
    for raw in keywords or []:
        kw = str(raw).strip()
        if not kw:
            continue
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            result.append(kw)
    return result


def normalize_folder_path(path: str) -> str:
    """Normalize folder separators to single backslashes."""
    return "\\".join(s.strip() for s in re.split(r"[\\/]", path or "") if s.strip())


@dataclass
class ParsedConfig:
    version: str = "3.0"
    settings: dict = field(default_factory=dict)
    stores: Dict[str, StoreConfig] = field(default_factory=dict)
    rules: List[RuleConfig] = field(default_factory=list)
    folders: List[str] = field(default_factory=list)
    unclassified: List[str] = field(default_factory=list)
    legacy_rule_names: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def unique_rule_id(path: str, taken: Iterable[str]) -> str:
    """'rule_<path lower>', with _2, _3... appended if that id is already used."""
    taken = set(taken)
    base = f"rule_{normalize_folder_path(path).lower()}"
    rid, n = base, 2
    while rid in taken:
        rid = f"{base}_{n}"
        n += 1
    return rid


def _is_inside_folder(path: str, root: str) -> bool:
    p = normalize_folder_path(path).lower()
    r = normalize_folder_path(root).lower()
    return bool(r) and (p == r or p.startswith(r + "\\"))


def parse_folders(data: Dict[str, Any], default_settings: Optional[dict] = None) -> ParsedConfig:
    """Parse a v3 'folders:' configuration dict into a ParsedConfig."""
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a mapping: <root>")

    warnings: List[str] = []
    raw_settings = data.get("settings")
    if raw_settings is None:
        settings = copy.deepcopy(default_settings or {})
    elif not isinstance(raw_settings, dict):
        raise ValueError("settings must be a mapping: settings")
    else:
        settings = copy.deepcopy(default_settings or {})
        settings.update(raw_settings)
    settings.pop("custom_folders", None)
    settings.pop("auto_rule_names", None)

    unclassified_folder = str(settings.get("unclassified_folder", "_Unclassified") or "_Unclassified")

    raw_stores = data.get("stores")
    if raw_stores is not None and not isinstance(raw_stores, dict):
        raise ValueError("stores must be a mapping: stores")
    stores: Dict[str, StoreConfig] = {}
    for s_id, s_data in (raw_stores or {}).items():
        if s_data is None:
            s_data = {}
        if not isinstance(s_data, dict):
            raise ValueError(f"Store entry must be a mapping: stores.{s_id}")
        stores[str(s_id)] = StoreConfig(
            id=str(s_id),
            name=str(s_data.get("name", s_id)),
            file_path=str(s_data.get("file_path", "") or ""),
            store_id=str(s_data.get("store_id", "") or ""),
        )

    raw_folders = data.get("folders")
    if raw_folders is not None and not isinstance(raw_folders, dict):
        raise ValueError("folders must be a mapping: folders")

    folders: List[str] = []
    rules: List[RuleConfig] = []
    seen_emails: Dict[str, str] = {}
    seen_domains: Dict[str, str] = {}

    def _visit_folder(name: str, value: Any, parent_path: str) -> None:
        clean_name = normalize_folder_path(str(name))
        path = f"{parent_path}\\{clean_name}" if parent_path else clean_name
        if not clean_name:
            warnings.append(f"Ignored folder with an empty name under: {parent_path or '<root>'}")
            return

        if any(seg.startswith("_") for seg in clean_name.split("\\")):
            warnings.append(f"Ignored folder starting with '_': {path}")
            return
        if _is_inside_folder(path, unclassified_folder):
            warnings.append(f"Ignored unclassified folder inside 'folders': {path}")
            return

        folders.append(path)
        emails: List[str] = []
        domains: List[str] = []
        keywords: List[str] = []
        enabled = True
        subfolders: List[Tuple[str, Any]] = []

        if value is None:
            pass
        elif isinstance(value, dict):
            for k, v in value.items():
                subfolders.append((str(k), v))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, str):
                    s = item.strip()
                    if not s:
                        continue
                    if any(ch.isspace() for ch in s):
                        warnings.append(
                            f"Ignored '{s}' in {path}: one sender per line, each starting with '- '"
                        )
                        continue
                    if s.startswith("@"):
                        dom = normalize_domain(s)
                        if not dom:
                            warnings.append(f"Ignored invalid domain '{item}' in {path}")
                            continue
                        if dom in seen_domains:
                            first = seen_domains[dom]
                            warnings.append(f"{dom}: in {first} and {path} - kept in {first}")
                        else:
                            seen_domains[dom] = path
                            domains.append(dom)
                    elif "@" in s:
                        local, dom_part = s.split("@", 1)
                        if not local.strip() or not dom_part.strip():
                            warnings.append(f"Ignored invalid sender '{item}' in {path}")
                            continue
                        email = s.lower()
                        if email in seen_emails:
                            first = seen_emails[email]
                            warnings.append(f"{email}: in {first} and {path} - kept in {first}")
                        else:
                            seen_emails[email] = path
                            emails.append(email)
                    else:
                        warnings.append(f"Ignored invalid sender '{item}' in {path}")
                elif isinstance(item, dict):
                    if len(item) != 1:
                        raise ValueError(f"Mapping item must have exactly 1 key: {path}[{idx}]")
                    k, v = next(iter(item.items()))
                    k_str = str(k)
                    if k_str.startswith("_"):
                        if k_str == "_subject":
                            if isinstance(v, str):
                                keywords.extend(normalize_keywords([v]))
                            elif isinstance(v, list):
                                for kw_item in v:
                                    if not isinstance(kw_item, str):
                                        raise ValueError(f"_subject items must be strings: {path}")
                                keywords.extend(normalize_keywords(v))
                            elif v is not None:
                                raise ValueError(f"_subject must be a string or list: {path}")
                        elif k_str == "_enabled":
                            if not isinstance(v, bool):
                                raise ValueError(f"_enabled must be a boolean: {path}")
                            enabled = v
                        else:
                            warnings.append(f"Ignored unknown option '{k_str}' in {path}")
                    else:
                        subfolders.append((k_str, v))
                else:
                    raise ValueError(f"Invalid item in folder list: {path}[{idx}]")
        elif isinstance(value, str):
            raise ValueError(
                f"Folder value must be a list, mapping, or null: {path} "
                f"(put '- ' before each sender, one per line)"
            )
        else:
            raise ValueError(f"Folder value must be a list, mapping, or null: {path}")

        keywords = normalize_keywords(keywords)
        if emails or domains or keywords:
            rules.append(RuleConfig(
                id=unique_rule_id(path, (r.id for r in rules)),
                name=rule_name_from_folder(path),
                enabled=enabled,
                emails=sorted(set(emails)),
                domains=sorted(set(domains)),
                subject_keywords=keywords,
                target_folder=path,
            ))

        for sub_name, sub_val in subfolders:
            _visit_folder(sub_name, sub_val, path)

    for top_name, top_val in (raw_folders or {}).items():
        _visit_folder(str(top_name), top_val, "")

    raw_unclassified = data.get("unclassified")
    if raw_unclassified is not None and not isinstance(raw_unclassified, list):
        raise ValueError("unclassified must be a list: unclassified")
    unclassified_list: List[str] = []
    seen_unc: Set[str] = set()
    for item in raw_unclassified or []:
        if not isinstance(item, str):
            raise ValueError("unclassified items must be strings: unclassified")
        em = item.strip().lower()
        if em and any(ch.isspace() for ch in em):
            warnings.append(f"Ignored '{em}' in unclassified: one sender per line, each starting with '- '")
            continue
        if em and em not in seen_unc:
            seen_unc.add(em)
            unclassified_list.append(em)

    rules.append(RuleConfig(
        id="rule_unclassified",
        name="[Unclassified]",
        enabled=True,
        emails=list(unclassified_list),
        domains=[],
        subject_keywords=[],
        target_folder=unclassified_folder,
    ))

    raw_legacy = data.get("legacy_rule_names")
    if raw_legacy is not None and not isinstance(raw_legacy, list):
        raise ValueError("legacy_rule_names must be a list: legacy_rule_names")
    legacy_rule_names: List[str] = []
    seen_leg: Set[str] = set()
    for item in raw_legacy or []:
        s = str(item).strip()
        if s and s not in seen_leg:
            seen_leg.add(s)
            legacy_rule_names.append(s)

    return ParsedConfig(
        version="3.0",
        settings=settings,
        stores=stores,
        rules=rules,
        folders=folders,
        unclassified=unclassified_list,
        legacy_rule_names=legacy_rule_names,
        warnings=warnings,
    )


def dump_folders(
    rules: List[RuleConfig],
    folders: List[str],
    unclassified: List[str],
    legacy_rule_names: List[str],
    settings: dict,
    stores: Dict[str, StoreConfig],
    version: str = "3.0",
) -> Dict[str, Any]:
    """Serialize rules, folder hierarchy, unclassified pool, and metadata into a v3 dict."""
    unclassified_folder = str(settings.get("unclassified_folder", "_Unclassified") or "_Unclassified")

    rules_by_folder: Dict[str, RuleConfig] = {}
    for r in rules:
        if r.id == "rule_unclassified" or _is_inside_folder(r.target_folder or "", unclassified_folder):
            continue
        norm_p = normalize_folder_path(r.target_folder or "")
        if norm_p:
            rules_by_folder[norm_p.lower()] = r

    # Preserve folder order, ensuring all parent segments and rule folders exist
    ordered_paths: List[str] = []
    seen_paths: Set[str] = set()

    def _register_path(path: str) -> None:
        norm = normalize_folder_path(path)
        if not norm or _is_inside_folder(norm, unclassified_folder):
            return
        parts = norm.split("\\")
        if any(p.startswith("_") for p in parts):
            return
        for i in range(1, len(parts) + 1):
            sub = "\\".join(parts[:i])
            low = sub.lower()
            if low not in seen_paths:
                seen_paths.add(low)
                ordered_paths.append(sub)

    for f in folders:
        _register_path(f)
    for r in rules:
        if r.id != "rule_unclassified" and not _is_inside_folder(r.target_folder or "", unclassified_folder):
            _register_path(r.target_folder or "")

    children_map: Dict[str, List[str]] = {"": []}
    canonical_name: Dict[str, str] = {}
    for p in ordered_paths:
        low = p.lower()
        canonical_name[low] = p.split("\\")[-1]
        children_map.setdefault(low, [])
        parent_low = "\\".join(p.split("\\")[:-1]).lower()
        children_map.setdefault(parent_low, []).append(low)

    def _build_node_list(folder_low: str) -> list:
        items: list = []
        rule = rules_by_folder.get(folder_low)
        if rule is not None:
            for e in sorted(set(e.strip().lower() for e in (rule.emails or []) if e.strip())):
                items.append(e)
            for d in sorted(set(normalize_domains(rule.domains or []))):
                items.append(d)
            kws = normalize_keywords(rule.subject_keywords or [])
            if kws:
                items.append({"_subject": kws})
            if not rule.enabled:
                items.append({"_enabled": False})
        for child_low in children_map.get(folder_low, []):
            items.append({canonical_name[child_low]: _build_node_list(child_low)})
        return items

    folders_dict: Dict[str, Any] = {}
    for top_low in children_map.get("", []):
        folders_dict[canonical_name[top_low]] = _build_node_list(top_low)

    clean_settings = {
        k: copy.deepcopy(v)
        for k, v in (settings or {}).items()
        if k not in ("custom_folders", "auto_rule_names")
    }

    stores_dict = {
        s_id: {
            "name": s.name,
            "file_path": s.file_path,
            **({"store_id": s.store_id} if s.store_id else {}),
        }
        for s_id, s in stores.items()
    }

    out: Dict[str, Any] = {
        "version": str(version or "3.0"),
        "settings": clean_settings,
        "stores": stores_dict,
        "folders": folders_dict,
        "unclassified": sorted(set(e.strip().lower() for e in (unclassified or []) if e and e.strip())),
    }
    clean_legacy = [str(n).strip() for n in (legacy_rule_names or []) if str(n).strip()]
    if clean_legacy:
        out["legacy_rule_names"] = list(dict.fromkeys(clean_legacy))
    return out


def migrate_v2_with_warnings(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Convert a v2 rules.yaml dict (with 'rules:' and 'groups:') into a v3 'folders:' dict."""
    warnings: List[str] = []
    settings_in = copy.deepcopy(data.get("settings") or {})
    unclassified_folder = str(settings_in.get("unclassified_folder", "_Unclassified") or "_Unclassified")
    custom_folders = list(settings_in.pop("custom_folders", []) or [])
    settings_in.pop("auto_rule_names", None)

    raw_stores = data.get("stores") or {}
    stores: Dict[str, StoreConfig] = {}
    for s_id, s_data in raw_stores.items():
        s_data = s_data or {}
        stores[s_id] = StoreConfig(
            id=s_id,
            name=s_data.get("name", s_id),
            file_path=s_data.get("file_path", "") or "",
            store_id=s_data.get("store_id", "") or "",
        )

    groups: Dict[str, Dict[str, Any]] = {}
    for g_id, g_data in (data.get("groups") or {}).items():
        g_data = g_data or {}
        groups[g_id] = {
            "name": g_data.get("name", g_id),
            "emails": [str(e).lower().strip() for e in (g_data.get("emails") or []) if str(e).strip()],
            "domains": normalize_domains(g_data.get("domains") or []),
        }

    raw_rules = data.get("rules") or []

    # Warn if any group is linked by multiple non-unclassified rules
    group_users: Dict[str, List[str]] = {}
    for r_data in raw_rules:
        if not isinstance(r_data, dict):
            continue
        r_id = r_data.get("id", "")
        r_folder = normalize_folder_path(r_data.get("target_folder", "") or "")
        if r_id == "rule_unclassified" or _is_inside_folder(r_folder, unclassified_folder):
            continue
        for g_id in (r_data.get("groups") or []):
            group_users.setdefault(g_id, []).append(r_data.get("name") or r_folder or r_id)
    for g_id, users in group_users.items():
        if len(users) > 1:
            g_name = groups.get(g_id, {}).get("name", g_id)
            warnings.append(
                f"Shared group '{g_name}' was linked to multiple rules ({', '.join(users)}); "
                f"its senders are kept in the first folder."
            )

    unclassified_emails: List[str] = [
        str(e).lower().strip() for e in (data.get("unclassified_pool") or []) if str(e).strip()
    ]
    legacy_rule_names: List[str] = []
    seen_legacy: Set[str] = set()

    def _add_legacy(name_val: str) -> None:
        s = (name_val or "").strip()
        if s and s not in seen_legacy:
            seen_legacy.add(s)
            legacy_rule_names.append(s)

    # Group non-unclassified rules by target folder (preserving first-seen order)
    folder_order: List[str] = []
    grouped_rules: Dict[str, List[Dict[str, Any]]] = {}

    for r_data in raw_rules:
        if not isinstance(r_data, dict):
            continue
        r_id = r_data.get("id", "")
        r_name = str(r_data.get("name", "") or "").strip()
        r_folder = normalize_folder_path(r_data.get("target_folder", "") or "")
        r_store = str(r_data.get("target_store", "active_archive") or "active_archive")

        # Collect emails + group emails
        r_emails = [str(e).lower().strip() for e in (r_data.get("emails") or []) if str(e).strip()]
        r_domains = normalize_domains(r_data.get("domains") or [])
        for g_id in (r_data.get("groups") or []):
            grp = groups.get(g_id)
            if grp:
                r_emails.extend(grp["emails"])
                r_domains.extend(grp["domains"])

        if r_id == "rule_unclassified" or _is_inside_folder(r_folder, unclassified_folder):
            unclassified_emails.extend(r_emails)
            if r_domains:
                warnings.append(
                    f"Domains of the unclassified rule were dropped (only emails can be unclassified): "
                    f"{', '.join(sorted(set(r_domains)))}"
                )
            continue

        if not r_folder:
            warnings.append(f"Rule '{r_name or r_id}' has no target_folder; skipped during migration.")
            continue

        if r_store and r_store != "active_archive":
            warnings.append(
                f"Rule '{r_name}' targeted store '{r_store}' (not active_archive); "
                f"imported into folder '{r_folder}'."
            )

        new_rule_name = rule_name_from_folder(r_folder)
        if r_name and r_name != new_rule_name:
            _add_legacy(r_name)
        for fn in (r_data.get("former_names") or []):
            fn_str = str(fn).strip()
            if fn_str and fn_str != new_rule_name:
                _add_legacy(fn_str)

        key = r_folder.lower()
        if key not in grouped_rules:
            grouped_rules[key] = []
            folder_order.append(r_folder)
        grouped_rules[key].append({
            "enabled": bool(r_data.get("enabled", True)),
            "emails": r_emails,
            "domains": r_domains,
            "subject_keywords": normalize_keywords(r_data.get("subject_keywords") or []),
            "folder": r_folder,
        })

    # Deduplicate senders globally (keep in first folder encountered, warn on duplicates)
    seen_emails: Dict[str, str] = {}
    seen_domains: Dict[str, str] = {}
    merged_rules: List[RuleConfig] = []

    for orig_folder in folder_order:
        key = orig_folder.lower()
        entries = grouped_rules[key]
        comb_emails: List[str] = []
        comb_domains: List[str] = []
        comb_keywords: List[str] = []
        any_enabled = False
        for ent in entries:
            if ent["enabled"]:
                any_enabled = True
            for e in ent["emails"]:
                if e in seen_emails:
                    if seen_emails[e].lower() != key:
                        warnings.append(f"{e}: in {seen_emails[e]} and {orig_folder} - kept in {seen_emails[e]}")
                else:
                    seen_emails[e] = orig_folder
                    comb_emails.append(e)
            for d in ent["domains"]:
                if d in seen_domains:
                    if seen_domains[d].lower() != key:
                        warnings.append(f"{d}: in {seen_domains[d]} and {orig_folder} - kept in {seen_domains[d]}")
                else:
                    seen_domains[d] = orig_folder
                    comb_domains.append(d)
            comb_keywords.extend(ent["subject_keywords"])

        comb_keywords = normalize_keywords(comb_keywords)
        if comb_emails or comb_domains or comb_keywords:
            merged_rules.append(RuleConfig(
                id=f"rule_{orig_folder.lower()}",
                name=rule_name_from_folder(orig_folder),
                enabled=any_enabled,
                emails=sorted(set(comb_emails)),
                domains=sorted(set(comb_domains)),
                subject_keywords=comb_keywords,
                target_folder=orig_folder,
            ))

    all_folders = list(folder_order)
    for cf in custom_folders:
        norm_cf = normalize_folder_path(str(cf))
        if norm_cf and not _is_inside_folder(norm_cf, unclassified_folder):
            all_folders.append(norm_cf)

    v3_dict = dump_folders(
        rules=merged_rules,
        folders=all_folders,
        unclassified=unclassified_emails,
        legacy_rule_names=legacy_rule_names,
        settings=settings_in,
        stores=stores,
        version="3.0",
    )
    return v3_dict, warnings


def migrate_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a v2 rules.yaml dict into a v3 'folders:' dict."""
    v3_dict, _ = migrate_v2_with_warnings(data)
    return v3_dict
