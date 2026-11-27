# Outlook Rule Companion 📨⚡

**Outlook Rule Companion** is an automation and management desktop assistant for Microsoft Outlook Classic. It simplifies creating, organizing, and maintaining email rules across annual PST archive files without replacing Outlook's native execution engine.

---

## 🌟 Key Features

- **Visual Folder Treeview & Drag-and-Drop Reorganization**: Browse hierarchical `Team \ Part \ Unit` folder trees visually. Reorganize rules and folders by dragging and dropping them directly between folders with instant YAML persistence.
- **Folder › Rule › Mail tree**: Every folder with a rule is one node — `📁 Directors  (rule: Management_Executive_Board_Directors)` — and the Inbox mails that rule catches (plus any subfolders) are listed under it. Click a mail to read it; drag it onto another rule or folder to re-route its sender. Rules are always named after their folder path (`Team\Part\Unit` → `Team_Part_Unit`).
- **Share rules (File › Export / Import)**: Export writes a copy of your rules and folders without your PST paths. Import either **merges** (same folder = senders added, other folders added) or **replaces** your rules; your PST paths are always kept and Ctrl+Z undoes the import.
- **Rule Studio & Inspector**: Dedicated clean cards for rules, folders, and the unclassified pool with breadcrumb navigation.
- **YAML Folder-Tree Configuration (`folders:`)**: Define folders, sender emails, `@domain` entries, `_subject` keywords, and `_enabled` flags directly in a clean `rules.yaml` tree. Manage thousands of addresses without Outlook's 64KB UI limitation.
- **Native Outlook Synchronization**: Outlook executes all rules natively (24/7 in the background, even when this companion app is closed). Sync YAML configurations directly into Outlook with one click.
- **Auto-Split Recipient Quotas**: Automatically splits oversized rules into sub-rules (`Rule (Part 1)`, `Rule (Part 2)`) to prevent Outlook RPC/quota errors.
- **1-Click Yearly PST Rollover**: Seamlessly re-point target folders of all active rules to a new year's PST file (`Archive 2025.pst`, `Archive 2026.pst`) in seconds.
- **Create a new PST (first year)**: In the Rollover dialog, *Create new PST...* creates an empty Unicode PST (suggested `Archive_<year>.pst` next to your open data files), opens it in Outlook and selects it. It never overwrites a file and refuses OneDrive/network paths; rules only change when you click *Execute 1-Click Rollover*.
- **Triage & Auto-Learning**: Inspect incoming Inbox emails, view attachments and body text, and assign senders/domains to rules with one click.
- **Exchange X.500 Resolution**: Automatically resolves internal company Exchange addresses (`/O=EXCHANGELABS/...`) to clean SMTP addresses.
- **Unclassified Pool**: When a rule is deleted, its addresses are safely retained in `unclassified` and routed to `_Unclassified` rather than cluttering your Inbox.
- **Cross-Platform**: Runs in full native COM mode on Windows with Outlook Classic, and in simulated Mock Mode on Linux/macOS for development and testing.

---

## 📄 Configuration Format (`config/rules.yaml`, v3.0)

`config/rules.yaml` mirrors your PST folder tree under `folders:`:

```yaml
version: '3.0'
settings:
  auto_split_threshold: 40
  unclassified_folder: _Unclassified
  backup_versions: 30
stores:
  active_archive:
    name: Archive 2025
    file_path: D:\Outlook_Data\longp_Archive_2025.pst
folders:
  Management: []                      # empty folder, no rule
  Engineering:
    - em@company.com                  # → rule [Companion] Engineering
    - Pol_Process:                    # → rule [Companion] Engineering_Pol_Process
        - employees1@company.com
        - employees2@company.com
        - "@techpartner.com"          # leading @ = domain
        - _subject: [PLC alarm, SCADA] # optional: subject keywords
        - _enabled: false             # optional: disable rule
unclassified:                         # senders routed to _Unclassified
  - former.contractor@vendor.com
legacy_rule_names:                    # old rule names (auto-generated on migration)
  - Executive Board
```

- **`_subject`**: List of subject keywords (or a single string) matched by the folder's rule.
- **`_enabled`**: Boolean (`true` by default). Set `false` to disable the folder's rule without removing its senders.
- **`unclassified`**: Emails routed to `settings.unclassified_folder` (`_Unclassified`).
- **`legacy_rule_names`**: Previous unprefixed Outlook rule names remembered during v2 → v3 migration so legacy cleanup can still find them.
- **One sender per line**: every email / `@domain` is its own `- ` item. Several addresses on one line are ignored with a warning; a folder whose senders have no `- ` at all is reported as an error with its path (the app shows it and does not start until the file is fixed).
- **A rule exists only while it has senders or `_subject`**: an empty rule (e.g. just created with New Rule) is saved as an empty folder.
- **Note on comments & v2 migration**: Comments in `rules.yaml` are not preserved when the app saves. Existing v2 files (with `rules:` / `groups:`) are automatically migrated to v3 on load after saving a one-time backup to `rules.yaml.v2.bak`.

---

## 🛠️ Requirements

- **Operating System**: Windows 10/11 (with Microsoft Outlook Classic: 2013, 2016, 2019, 2021, or Microsoft 365 ProPlus Desktop).
  *(Note: New Outlook for Windows WebView2 is not supported by Microsoft COM).*
- **Python**: Version 3.10+
- **Dependencies**: Listed in `requirements.txt` (`pyyaml`, `openpyxl`, `pywin32`).

---

## 🚀 Quick Start

### On Windows
1. Double-click `run_app.bat`.
2. Or run via Command Prompt:
   ```cmd
   pip install -r requirements.txt
   python main.py
   ```

### On Linux / macOS (Dev / Simulation Mode)
1. Run:
   ```bash
   ./run_app.sh
   # or: python3 main.py
   ```

---

## 📁 Project Structure

```
outlook-rule-manager/
├── config/
│   ├── rules.yaml               # Active configuration (Folders, Rules, Stores)
│   └── backups/                 # Versioned automatic backups
├── core/
│   ├── models.py                # Data classes
│   ├── config_format.py         # v3 folders: parser, serializer, and v2 migrator
│   ├── address_resolver.py      # X.500 to SMTP & email normalization
│   ├── yaml_manager.py          # YAML manager with versioned backups
│   ├── rule_splitter.py         # Quota protection & rule splitter
│   ├── outlook_client.py        # COM MAPI client & Linux mock client
│   └── sync_engine.py           # Synchronization & Specificity matching engine
├── gui/
│   ├── main_window.py           # Root window, tabs & quick sync
│   ├── triage_view.py           # 3-Pane Inbox inspector & rule assigner
│   ├── rule_manager_view.py     # Rule & Folder CRUD and Excel importer
│   ├── rollover_view.py         # PST Year Rollover wizard & size monitor
│   └── dryrun_view.py           # Simulation engine (Inbox test run)
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── run_app.bat                  # Windows launch script
└── run_app.sh                   # Linux launch script
```

