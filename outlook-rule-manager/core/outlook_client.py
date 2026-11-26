"""Outlook MAPI COM Interface and Cross-Platform Mock Client."""
import sys
import os
import re
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime

from core.models import EmailMessage, MANAGED_PREFIX, extract_base_rule_name
from core.address_resolver import resolve_outlook_sender, normalize_email

IS_WINDOWS = sys.platform == "win32"

try:
    if IS_WINDOWS:
        import win32com.client
        import pythoncom
    else:
        win32com = None
except ImportError:
    win32com = None


def _match_store_exact(stores, identifier: str, get_path, get_name):
    """Match a store by exact normalized FilePath, then exact DisplayName (case-insensitive)."""
    ident = (identifier or "").strip()
    norm_ident_path = os.path.normcase(os.path.normpath(ident))
    ident_lower = ident.lower()

    for s in stores:
        p = (get_path(s) or "").strip()
        if p and os.path.normcase(os.path.normpath(p)) == norm_ident_path:
            return s

    for s in stores:
        n = (get_name(s) or "").strip()
        if n and n.lower() == ident_lower:
            return s

    return None


class BaseOutlookClient:
    """Interface for Outlook operations."""
    def is_connected(self) -> bool:
        raise NotImplementedError
    def get_mode_name(self) -> str:
        raise NotImplementedError
    def get_current_user_account(self) -> str:
        raise NotImplementedError
    def get_stores(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def get_inbox_messages(self, limit: int = 50) -> List[EmailMessage]:
        raise NotImplementedError
    def get_native_rules(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def store_exists(self, identifier: str) -> bool:
        raise NotImplementedError
    def save_native_rules(
        self,
        rules_data: List[Dict[str, Any]],
        target_store_path: str,
        remove_legacy: bool = False,
        legacy_base_names: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        raise NotImplementedError
    def move_message(self, entry_id: str, target_folder_path: str, store_path: str = "") -> bool:
        raise NotImplementedError


class WindowsOutlookClient(BaseOutlookClient):
    """Native Windows Outlook Classic COM Client."""

    def __init__(self, namespace=None):
        self.app = None
        self.namespace = namespace
        self._connected = namespace is not None
        self._cached_account = ""
        if namespace is None:
            self._init_com()

    def _init_com(self):
        try:
            pythoncom.CoInitialize()
            self.app = win32com.client.Dispatch("Outlook.Application")
            self.namespace = self.app.GetNamespace("MAPI")
            self._connected = True
        except Exception:
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_mode_name(self) -> str:
        return "Outlook Classic (COM MAPI)"

    def get_current_user_account(self) -> str:
        """Fetch active user email or profile name from MAPI."""
        if not self._connected:
            return os.environ.get("USERNAME", "DefaultUser")
        if self._cached_account:
            return self._cached_account
        try:
            user = self.namespace.CurrentUser
            addr = getattr(user, "Address", "")
            name = getattr(user, "Name", "")
            if "@" in addr:
                self._cached_account = addr.lower()
            elif name:
                self._cached_account = name
            else:
                self._cached_account = os.environ.get("USERNAME", "DefaultUser")
        except Exception:
            self._cached_account = os.environ.get("USERNAME", "DefaultUser")
        return self._cached_account

    def get_stores(self) -> List[Dict[str, Any]]:
        """Scan all mounted stores/data files in Outlook with detailed metadata."""
        if not self._connected:
            return []
        stores_list = []
        try:
            for store in self.namespace.Stores:
                try:
                    name = store.DisplayName
                    path = getattr(store, "FilePath", "") or ""
                    store_id = store.StoreID
                    is_datafile = store.IsDataFileStore

                    # Calculate size if physical file exists
                    size_gb = 0.0
                    if path and os.path.exists(path):
                        size_gb = round(os.path.getsize(path) / (1024 ** 3), 2)

                    # List root folders
                    subfolders = []
                    try:
                        for f in store.GetRootFolder().Folders:
                            subfolders.append(f.Name)
                    except Exception:
                        pass

                    stores_list.append({
                        "name": name,
                        "file_path": path,
                        "store_id": store_id,
                        "is_data_file": is_datafile,
                        "size_gb": size_gb,
                        "folders": subfolders
                    })
                except Exception:
                    continue
        except Exception:
            pass
        return stores_list

    def _find_store(self, identifier: str):
        """Find store by exact normalized FilePath or exact DisplayName (case-insensitive).

        Returns DefaultStore only when identifier is empty; returns None if not found.
        """
        if not self._connected:
            return None
        if not (identifier or "").strip():
            return self.namespace.DefaultStore
        return _match_store_exact(
            self.namespace.Stores,
            identifier,
            lambda s: getattr(s, "FilePath", ""),
            lambda s: getattr(s, "DisplayName", ""),
        )

    def store_exists(self, identifier: str) -> bool:
        """Return True if a non-empty store identifier resolves to a mounted Outlook store."""
        if not self._connected or not (identifier or "").strip():
            return False
        return self._find_store(identifier) is not None

    def get_inbox_messages(self, limit: int = 50) -> List[EmailMessage]:
        if not self._connected:
            return []
        messages = []
        try:
            inbox = self.namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)

            count = 0
            for item in items:
                if count >= limit:
                    break
                try:
                    if getattr(item, "Class", 0) != 43:
                        continue

                    sender_name, sender_email = resolve_outlook_sender(item)
                    subject = getattr(item, "Subject", "(No Subject)") or "(No Subject)"
                    rec_time = getattr(item, "ReceivedTime", None)
                    if not isinstance(rec_time, datetime):
                        rec_time = datetime.now()

                    body = getattr(item, "Body", "") or ""
                    has_attach = getattr(item, "Attachments", None) and item.Attachments.Count > 0
                    is_read = not getattr(item, "UnRead", False)
                    entry_id = getattr(item, "EntryID", "")

                    messages.append(EmailMessage(
                        entry_id=entry_id,
                        subject=subject,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        received_time=rec_time,
                        body=body[:5000],
                        has_attachments=has_attach,
                        is_read=is_read
                    ))
                    count += 1
                except Exception:
                    continue
        except Exception:
            pass
        return messages

    def get_native_rules(self) -> List[Dict[str, Any]]:
        """Fetch all existing rules with their conditions & recipients from Outlook."""
        if not self._connected:
            return []
        result = []
        try:
            rules_col = self.namespace.DefaultStore.GetRules()
            for rule in rules_col:
                name = getattr(rule, "Name", "")
                enabled = getattr(rule, "Enabled", True)
                target_folder = ""
                emails = []

                # Target Folder
                try:
                    move_action = rule.Actions.MoveToFolder
                    if move_action.Enabled and move_action.Folder:
                        target_folder = move_action.Folder.FolderPath
                except Exception:
                    pass

                # Recipients in From condition
                try:
                    from_cond = rule.Conditions.From
                    if from_cond.Enabled:
                        for recip in from_cond.Recipients:
                            addr = getattr(recip, "Address", "")
                            if addr and "@" in addr:
                                emails.append(addr.lower().strip())
                            else:
                                name_recip = getattr(recip, "Name", "")
                                if name_recip:
                                    emails.append(name_recip.lower().strip())
                except Exception:
                    pass

                result.append({
                    "name": name,
                    "enabled": enabled,
                    "target_folder": target_folder,
                    "emails": emails
                })
        except Exception:
            pass
        return result

    def get_or_create_folder(self, root_store, folder_path: str):
        clean_path = folder_path.replace("\\", "/").strip("/")
        parts = [p.strip() for p in clean_path.split("/") if p.strip()]
        if not parts:
            return root_store.GetRootFolder()

        current = root_store.GetRootFolder()
        for part in parts:
            safe_name = re.sub(r'[\/:*?"<>|]', '_', part)
            found = None
            try:
                for sub in current.Folders:
                    if sub.Name.lower() == safe_name.lower():
                        found = sub
                        break
            except Exception:
                pass

            if found is None:
                current = current.Folders.Add(safe_name)
            else:
                current = found
        return current

    def save_native_rules(
        self,
        rules_data: List[Dict[str, Any]],
        target_store_path: str,
        remove_legacy: bool = False,
        legacy_base_names: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        if not self._connected:
            return False, "Outlook COM not connected"

        try:
            store = self.namespace.DefaultStore
            target_store = self._find_store(target_store_path)
            if target_store is None:
                return False, f"Target store not found: {target_store_path}"
            rules_col = store.GetRules()

            # Snapshot existing rules before any mutation/removal (COM iter skips on Remove)
            existing_rules: Dict[str, Any] = {}
            for r in rules_col:
                existing_rules[r.Name] = r

            created_count = 0
            updated_count = 0
            disabled_count = 0
            removed_count = 0
            warnings: List[str] = []
            valid_rules: List[Tuple[Dict[str, Any], List[str], List[str], List[str]]] = []
            compiled_names = set()

            for r_info in rules_data:
                r_name = r_info["name"]
                enabled = r_info.get("enabled", True)
                emails = [e for e in (r_info.get("emails") or []) if e]
                domains = [d for d in (r_info.get("domains") or []) if d]
                keywords = [k for k in (r_info.get("subject_keywords") or []) if k]

                # Safety check: never create or enable a condition-less Outlook rule
                if not emails and not domains and not keywords:
                    existing_rule = existing_rules.get(r_name)
                    if existing_rule is not None:
                        existing_rule.Enabled = False
                        disabled_count += 1
                    warnings.append(r_name)
                    continue

                compiled_names.add(r_name)
                valid_rules.append((r_info, emails, domains, keywords))

            yaml_base_names = set(legacy_base_names or [])
            if not yaml_base_names:
                yaml_base_names = {extract_base_rule_name(name) for name in compiled_names}

            managed_to_remove: List[str] = []
            legacy_to_clean: List[str] = []
            legacy_to_remove: List[str] = []
            disabled_broken_legacy: List[str] = []

            for existing_name, existing_rule in list(existing_rules.items()):
                if existing_name.startswith(MANAGED_PREFIX):
                    if existing_name not in compiled_names:
                        managed_to_remove.append(existing_name)
                    continue

                if existing_name in compiled_names:
                    continue

                if extract_base_rule_name(existing_name) in yaml_base_names:
                    if self._is_conditionless_move_rule(existing_rule):
                        was_enabled = bool(getattr(existing_rule, "Enabled", False))
                        existing_rule.Enabled = False
                        if was_enabled:
                            disabled_count += 1
                            disabled_broken_legacy.append(existing_name)
                    if remove_legacy:
                        legacy_to_remove.append(existing_name)
                    else:
                        legacy_to_clean.append(existing_name)

            # Collect names first, then Remove to avoid mutating COM collection while iterating
            for name_to_remove in managed_to_remove + legacy_to_remove:
                rules_col.Remove(name_to_remove)
                existing_rules.pop(name_to_remove, None)
                removed_count += 1

            unprefixed_remaining = sum(
                1 for name in existing_rules if not name.startswith(MANAGED_PREFIX)
            )
            managed_order = 1
            for r_info, emails, domains, keywords in valid_rules:
                r_name = r_info["name"]
                enabled = r_info.get("enabled", True)
                target_folder_path = r_info.get("target_folder", "")

                rule = existing_rules.get(r_name)
                if not rule:
                    rule = rules_col.Create(r_name, 0)
                    existing_rules[r_name] = rule
                    created_count += 1
                else:
                    updated_count += 1

                rule.Enabled = enabled
                if not enabled:
                    disabled_count += 1

                from_cond = rule.Conditions.From
                while from_cond.Recipients.Count > 0:
                    from_cond.Recipients.Remove(1)
                if emails:
                    from_cond.Enabled = True
                    for e in emails:
                        from_cond.Recipients.Add(e)
                    try:
                        from_cond.Recipients.ResolveAll()
                    except Exception:
                        pass
                else:
                    from_cond.Enabled = False

                sender_cond = rule.Conditions.SenderAddress
                if domains:
                    sender_cond.Address = list(domains)
                    sender_cond.Enabled = True
                else:
                    sender_cond.Enabled = False
                    try:
                        sender_cond.Address = []
                    except Exception:
                        pass

                subj_cond = rule.Conditions.Subject
                if keywords:
                    subj_cond.Text = list(keywords)
                    subj_cond.Enabled = True
                else:
                    subj_cond.Enabled = False
                    try:
                        subj_cond.Text = []
                    except Exception:
                        pass

                if target_folder_path:
                    target_folder_obj = self.get_or_create_folder(target_store, target_folder_path)
                    move_act = rule.Actions.MoveToFolder
                    move_act.Enabled = True
                    move_act.Folder = target_folder_obj

                if r_name.startswith(MANAGED_PREFIX):
                    try:
                        rule.Actions.Stop.Enabled = True
                    except Exception:
                        pass
                    try:
                        rule.ExecutionOrder = unprefixed_remaining + managed_order
                    except Exception:
                        pass
                    managed_order += 1

            rules_col.Save(ShowProgress=False)
            msg = (
                f"Successfully synced rules to Outlook "
                f"(Created: {created_count}, Updated: {updated_count}, "
                f"Disabled: {disabled_count}, Removed: {removed_count})"
            )
            if disabled_broken_legacy:
                msg += f"\nDisabled broken condition-less legacy rules: {', '.join(disabled_broken_legacy)}"
            if legacy_to_clean:
                msg += f"\nLegacy rules pending cleanup: {', '.join(legacy_to_clean)}"
            if warnings:
                msg += f"\nWarning - skipped rules with no conditions: {', '.join(warnings)}"
            return True, msg
        except Exception as ex:
            return False, f"Failed to sync rules to Outlook: {str(ex)}"

    @staticmethod
    def _is_conditionless_move_rule(rule) -> bool:
        """Return True only when no condition is enabled while MoveToFolder is enabled."""
        try:
            conds = rule.Conditions
            count = conds.Count
            any_enabled = False
            for i in range(1, count + 1):
                if getattr(conds.Item(i), "Enabled", False):
                    any_enabled = True
                    break
            move_on = bool(getattr(getattr(rule.Actions, "MoveToFolder", None), "Enabled", False))
            return (not any_enabled) and move_on
        except Exception:
            return False

    def move_message(self, entry_id: str, target_folder_path: str, store_path: str = "") -> bool:
        if not self._connected:
            return False
        try:
            target_store = self._find_store(store_path)
            if target_store is None:
                return False
            mail = self.namespace.GetItemFromID(entry_id)
            folder = self.get_or_create_folder(target_store, target_folder_path)
            mail.Move(folder)
            return True
        except Exception:
            return False


class MockOutlookClient(BaseOutlookClient):
    """Mock Outlook Client for Linux/macOS testing and development."""

    def __init__(self):
        self._account = "longp@company.com"
        self._stores = [
            {
                "name": "longp Archive 2024",
                "file_path": "/mock/data/longp_Archive_2024.pst",
                "store_id": "STORE_2024",
                "is_data_file": True,
                "size_gb": 18.5,
                "folders": ["Executive_Board", "Engineering", "Suppliers", "_Unclassified"]
            },
            {
                "name": "longp Archive 2025",
                "file_path": "/mock/data/longp_Archive_2025.pst",
                "store_id": "STORE_2025",
                "is_data_file": True,
                "size_gb": 4.2,
                "folders": ["Engineering", "Suppliers"]
            },
            {
                "name": "Primary Mailbox - longp",
                "file_path": "",
                "store_id": "PRIMARY_STORE",
                "is_data_file": False,
                "size_gb": 2.1,
                "folders": ["Inbox", "Sent Items", "Deleted Items"]
            },
        ]
        self._rules = [
            {
                "name": "Executive Board",
                "enabled": True,
                "target_folder": "Archive 2024\\Executive_Board",
                "emails": ["ceo@company.com", "coo@company.com"]
            },
            {
                "name": "Engineering",
                "enabled": True,
                "target_folder": "Archive 2024\\Engineering",
                "emails": ["eng1@company.com", "eng2@company.com", "lead.scada@company.com"]
            },
            {
                "name": "Old Vendor Rule (Legacy)",
                "enabled": True,
                "target_folder": "Inbox\\OldVendors",
                "emails": ["sales@vendor.com"]
            }
        ]
        self._inbox = [
            EmailMessage(
                entry_id="MSG_001",
                subject="URGENT: SCADA PLC communication timeout on Line 3",
                sender_name="Nguyen Van Bach (Maintenance)",
                sender_email="lead.scada@company.com",
                received_time=datetime.now(),
                body=(
                    "Dear Team,\n\n"
                    "The CP1E PLC lost connection during the night shift. "
                    "Error code: COMM_TIMEOUT_0x4F. Please review trace log.\n\n"
                    "Attachments: scada_tracelog_20261109.csv\n\n"
                    "Best regards,\nNguyen Van Bach"
                ),
                has_attachments=True,
                is_read=False
            ),
            EmailMessage(
                entry_id="MSG_002",
                subject="Quote for Omron Photoelectric Sensors E3Z-D61",
                sender_name="Pham Thu Ha (Omron Sales)",
                sender_email="ha.pham@omron.com",
                received_time=datetime.now(),
                body=(
                    "Dear Purchasing Manager,\n\n"
                    "Thank you for contacting Omron Electronics. "
                    "Attached is the official quotation for 50 pcs sensor E3Z-D61 with 2 weeks lead time.\n\n"
                    "Payment term: 30 days net.\n\n"
                    "Best regards,\nPham Thu Ha\nOmron Vietnam"
                ),
                has_attachments=True,
                is_read=False
            ),
            EmailMessage(
                entry_id="MSG_003",
                subject="Monthly Production KPI Meeting - Q4",
                sender_name="Tran Duc Huy (COO)",
                sender_email="coo@company.com",
                received_time=datetime.now(),
                body=(
                    "All department heads,\n\n"
                    "The Q4 performance review is scheduled for this Friday at 9:00 AM in Meeting Room A.\n"
                    "Please prepare your KPI slides.\n\n"
                    "Regards,\nTran Duc Huy - COO"
                ),
                has_attachments=False,
                is_read=True
            ),
            EmailMessage(
                entry_id="MSG_004",
                subject="New Vendor Partnership Inquiry",
                sender_name="Kenji Sato (Sato Automation)",
                sender_email="sato@sato-automation.jp",
                received_time=datetime.now(),
                body=(
                    "Hello Antigravity Team,\n\n"
                    "We would like to introduce our latest industrial IoT gateway compatible with Nexacro EMS and Omron PLCs.\n"
                    "Would you be open for a 15-minute introductory call next Tuesday?\n\n"
                    "Sincerely,\nKenji Sato\nSato Automation Tokyo"
                ),
                has_attachments=False,
                is_read=False
            ),
            EmailMessage(
                entry_id="MSG_005",
                subject="Delivery notice for replacement spare parts",
                sender_name="Contractor Support",
                sender_email="former.contractor@vendor.com",
                received_time=datetime.now(),
                body=(
                    "Shipment #9921 has arrived at Gate 2.\n"
                    "Items: 4x Pneumatic cylinders, 10x Solenoid valves.\n"
                    "Please assign personnel to inspect.\n\n"
                    "Thanks."
                ),
                has_attachments=False,
                is_read=False
            ),
        ]

    def is_connected(self) -> bool:
        return True

    def get_mode_name(self) -> str:
        return "Simulated Mock Mode (Dev/Linux)"

    def get_current_user_account(self) -> str:
        return self._account

    def get_stores(self) -> List[Dict[str, Any]]:
        return self._stores

    def get_inbox_messages(self, limit: int = 50) -> List[EmailMessage]:
        return self._inbox[:limit]

    def get_native_rules(self) -> List[Dict[str, Any]]:
        return self._rules

    def _find_store(self, identifier: str) -> Optional[Dict[str, Any]]:
        if not (identifier or "").strip():
            return self._stores[-1] if self._stores else None
        return _match_store_exact(
            self._stores,
            identifier,
            lambda s: s.get("file_path", ""),
            lambda s: s.get("name", ""),
        )

    def store_exists(self, identifier: str) -> bool:
        if not (identifier or "").strip():
            return False
        return self._find_store(identifier) is not None

    def save_native_rules(
        self,
        rules_data: List[Dict[str, Any]],
        target_store_path: str,
        remove_legacy: bool = False,
        legacy_base_names: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        target_store = self._find_store(target_store_path)
        if target_store is None:
            return False, f"Target store not found: {target_store_path}"

        yaml_base_names = set(legacy_base_names or [])
        compiled_names = {r["name"] for r in rules_data}
        if not yaml_base_names:
            yaml_base_names = {extract_base_rule_name(name) for name in compiled_names}

        preserved_rules = []
        legacy_to_clean = []
        removed_count = 0
        for old_r in self._rules:
            old_name = old_r.get("name", "")
            if old_name.startswith(MANAGED_PREFIX):
                if old_name not in compiled_names:
                    removed_count += 1
                continue
            if old_name in compiled_names:
                continue
            if extract_base_rule_name(old_name) in yaml_base_names:
                if remove_legacy:
                    removed_count += 1
                    continue
                legacy_to_clean.append(old_name)
            preserved_rules.append(old_r)

        new_rules = []
        warnings = []
        for r in rules_data:
            emails = [e for e in (r.get("emails") or []) if e]
            domains = [d for d in (r.get("domains") or []) if d]
            keywords = [k for k in (r.get("subject_keywords") or []) if k]
            if not emails and not domains and not keywords:
                warnings.append(r["name"])
                continue
            new_rules.append({
                "name": r["name"],
                "enabled": r.get("enabled", True),
                "target_folder": f"{target_store_path}\\{r.get('target_folder', '')}",
                "emails": emails,
                "domains": domains,
                "subject_keywords": keywords,
            })
        self._rules = new_rules + preserved_rules
        msg = f"Mock: Successfully synced {len(new_rules)} rules to Outlook (Removed: {removed_count})"
        if legacy_to_clean:
            msg += f"\nLegacy rules pending cleanup: {', '.join(legacy_to_clean)}"
        if warnings:
            msg += f"\nWarning - skipped rules with no conditions: {', '.join(warnings)}"
        return True, msg

    def move_message(self, entry_id: str, target_folder_path: str, store_path: str = "") -> bool:
        if self._find_store(store_path) is None:
            return False
        self._inbox = [m for m in self._inbox if m.entry_id != entry_id]
        return True


def get_outlook_client() -> BaseOutlookClient:
    """Factory to get native Windows Outlook client or Mock client on Linux."""
    if IS_WINDOWS and win32com is not None:
        try:
            client = WindowsOutlookClient()
            if client.is_connected():
                return client
        except Exception:
            pass
    return MockOutlookClient()
