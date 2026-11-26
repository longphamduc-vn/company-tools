"""Minimal fake Outlook COM objects for unit testing WindowsOutlookClient without Outlook."""
from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class FakeRecipient:
    """Fake Outlook COM Recipient."""
    Address: str
    Name: str = ""
    Resolved: bool = True

    def __post_init__(self):
        if not self.Name:
            self.Name = self.Address


class FakeRecipients:
    """Fake Outlook COM Recipients collection (1-based Remove indexing)."""

    def __init__(self, resolve_success: bool = True, unresolved_addresses: Optional[set] = None):
        self._items: List[FakeRecipient] = []
        self.resolve_success = resolve_success
        self.unresolved_addresses = set(unresolved_addresses or ())

    def Add(self, address_or_name: str) -> FakeRecipient:
        is_resolved = address_or_name not in self.unresolved_addresses
        recip = FakeRecipient(Address=address_or_name, Name=address_or_name, Resolved=is_resolved)
        self._items.append(recip)
        return recip

    def Remove(self, index: int) -> None:
        if not isinstance(index, int) or index < 1 or index > len(self._items):
            raise IndexError(f"Recipient index out of range: {index}")
        self._items.pop(index - 1)

    @property
    def Count(self) -> int:
        return len(self._items)

    def ResolveAll(self) -> bool:
        all_ok = self.resolve_success
        for recip in self._items:
            if recip.Address in self.unresolved_addresses:
                recip.Resolved = False
                all_ok = False
            else:
                recip.Resolved = self.resolve_success
        return all_ok

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


@dataclass
class FakeFromCondition:
    """Fake Rule.Conditions.From."""
    Enabled: bool = False
    Recipients: FakeRecipients = field(default_factory=FakeRecipients)


@dataclass
class FakeSenderAddressCondition:
    """Fake Rule.Conditions.SenderAddress."""
    Enabled: bool = False
    Address: List[str] = field(default_factory=list)


@dataclass
class FakeSubjectCondition:
    """Fake Rule.Conditions.Subject."""
    Enabled: bool = False
    Text: List[str] = field(default_factory=list)


@dataclass
class FakeSentToCondition:
    """Fake Rule.Conditions.SentTo."""
    Enabled: bool = False
    Recipients: FakeRecipients = field(default_factory=FakeRecipients)


@dataclass
class FakeBodyCondition:
    """Fake Rule.Conditions.Body."""
    Enabled: bool = False
    Text: List[str] = field(default_factory=list)


@dataclass
class FakeConditions:
    """Fake Rule.Conditions supporting Count and 1-based Item(index)."""
    From: FakeFromCondition = field(default_factory=FakeFromCondition)
    SenderAddress: FakeSenderAddressCondition = field(default_factory=FakeSenderAddressCondition)
    Subject: FakeSubjectCondition = field(default_factory=FakeSubjectCondition)
    SentTo: FakeSentToCondition = field(default_factory=FakeSentToCondition)
    Body: FakeBodyCondition = field(default_factory=FakeBodyCondition)

    def _all_conditions(self):
        return [self.From, self.SenderAddress, self.Subject, self.SentTo, self.Body]

    @property
    def Count(self) -> int:
        return len(self._all_conditions())

    def Item(self, index: int):
        items = self._all_conditions()
        if not isinstance(index, int) or index < 1 or index > len(items):
            raise IndexError(f"Condition index out of range: {index}")
        return items[index - 1]


@dataclass
class FakeMoveToFolderAction:
    """Fake Rule.Actions.MoveToFolder."""
    Enabled: bool = False
    Folder: Optional["FakeFolder"] = None


@dataclass
class FakeStopAction:
    """Fake Rule.Actions.Stop."""
    Enabled: bool = False


@dataclass
class FakeActions:
    """Fake Rule.Actions."""
    MoveToFolder: FakeMoveToFolderAction = field(default_factory=FakeMoveToFolderAction)
    Stop: FakeStopAction = field(default_factory=FakeStopAction)


class FakeRule:
    """Fake Outlook COM Rule."""

    def __init__(self, name: str, rule_type: int = 0, enabled: bool = True, execution_order: int = 1):
        self.Name = name
        self.RuleType = rule_type
        self.Enabled = enabled
        self.ExecutionOrder = execution_order
        self.Conditions = FakeConditions()
        self.Actions = FakeActions()


class FakeRules:
    """Fake Outlook COM Rules collection."""

    def __init__(self, initial_rules: Optional[List[FakeRule]] = None):
        self._rules: List[FakeRule] = list(initial_rules or [])
        self.saved_count: int = 0
        self.last_show_progress: Optional[bool] = None

    @property
    def Count(self) -> int:
        return len(self._rules)

    def Create(self, name: str, rule_type: int = 0) -> FakeRule:
        rule = FakeRule(name=name, rule_type=rule_type, execution_order=len(self._rules) + 1)
        self._rules.append(rule)
        return rule

    def Remove(self, index_or_name: Union[int, str]) -> None:
        if isinstance(index_or_name, int):
            if index_or_name < 1 or index_or_name > len(self._rules):
                raise IndexError(f"Rule index out of range: {index_or_name}")
            self._rules.pop(index_or_name - 1)
            return

        for idx, rule in enumerate(self._rules):
            if rule.Name == index_or_name:
                self._rules.pop(idx)
                return
        raise KeyError(f"Rule not found: {index_or_name}")

    def Save(self, ShowProgress: bool = False) -> None:
        self.saved_count += 1
        self.last_show_progress = ShowProgress

    def __iter__(self):
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)


class FakeFolderCollection:
    """Fake Outlook COM Folders collection."""

    def __init__(self, parent_path: str):
        self._parent_path = parent_path
        self._folders: List["FakeFolder"] = []

    def Add(self, name: str) -> "FakeFolder":
        if any(f.Name.lower() == name.lower() for f in self._folders):
            raise ValueError(f"Folder already exists: {name}")
        folder_path = f"{self._parent_path}\\{name}" if self._parent_path else name
        folder = FakeFolder(Name=name, FolderPath=folder_path)
        self._folders.append(folder)
        return folder

    @property
    def Count(self) -> int:
        return len(self._folders)

    def __iter__(self):
        return iter(self._folders)

    def __len__(self) -> int:
        return len(self._folders)


class FakeFolder:
    """Fake Outlook COM MAPIFolder."""

    def __init__(self, Name: str, FolderPath: Optional[str] = None):
        self.Name = Name
        self.FolderPath = FolderPath if FolderPath is not None else f"\\\\{Name}"
        self.Folders = FakeFolderCollection(self.FolderPath)


class FakeStore:
    """Fake Outlook COM Store."""

    def __init__(
        self,
        display_name: str,
        file_path: str = "",
        store_id: str = "",
        is_data_file: bool = True,
        rules: Optional[FakeRules] = None,
        root_folder: Optional[FakeFolder] = None,
    ):
        self.DisplayName = display_name
        self.FilePath = file_path
        self.StoreID = store_id or f"STORE_{display_name}"
        self.IsDataFileStore = is_data_file
        self._rules = rules if rules is not None else FakeRules()
        self._root_folder = root_folder if root_folder is not None else FakeFolder(
            Name=display_name, FolderPath=f"\\\\{display_name}"
        )

    def GetRootFolder(self) -> FakeFolder:
        return self._root_folder

    def GetRules(self) -> FakeRules:
        return self._rules


@dataclass
class FakeCurrentUser:
    """Fake Outlook COM Recipient for Namespace.CurrentUser."""
    Name: str = "Test User"
    Address: str = "test@company.com"


class FakeNamespace:
    """Fake Outlook COM MAPI Namespace."""

    def __init__(
        self,
        stores: Optional[List[FakeStore]] = None,
        default_store: Optional[FakeStore] = None,
        current_user: Optional[FakeCurrentUser] = None,
    ):
        if stores is None:
            if default_store is not None:
                self.Stores = [default_store]
            else:
                self.Stores = [FakeStore("Primary Mailbox", "", is_data_file=False)]
        else:
            self.Stores = list(stores)

        self.DefaultStore = default_store if default_store is not None else self.Stores[0]
        self.CurrentUser = current_user if current_user is not None else FakeCurrentUser()
        self._items: dict = {}

    def GetDefaultFolder(self, folder_type: int) -> FakeFolder:
        return self.DefaultStore.GetRootFolder()

    def GetItemFromID(self, entry_id: str):
        return self._items[entry_id]
