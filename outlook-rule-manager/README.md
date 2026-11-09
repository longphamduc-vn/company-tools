# Outlook Rule Companion 📨⚡

**Outlook Rule Companion** is an automation and management desktop assistant for Microsoft Outlook Classic. It simplifies creating, organizing, and maintaining email rules across annual PST archive files without replacing Outlook's native execution engine.

---

## 🌟 Key Features

- **YAML Rule & Group Management**: Define rules, reusable address groups, and domains in a clean `rules.yaml` file. Manage thousands of addresses without Outlook's 64KB UI limitation.
- **Native Outlook Synchronization**: Outlook executes all rules natively (24/7 in the background, even when this companion app is closed). Sync YAML configurations directly into Outlook with one click.
- **Auto-Split Recipient Quotas**: Automatically splits oversized rules into sub-rules (`Rule (Part 1)`, `Rule (Part 2)`) to prevent Outlook RPC/quota errors.
- **1-Click Yearly PST Rollover**: Seamlessly re-point target folders of all active rules to a new year's PST file (`Archive 2025.pst`, `Archive 2026.pst`) in seconds.
- **Triage & Auto-Learning**: Inspect incoming Inbox emails, view attachments and body text, and assign senders/domains to rules with one click.
- **Exchange X.500 Resolution**: Automatically resolves internal company Exchange addresses (`/O=EXCHANGELABS/...`) to clean SMTP addresses.
- **Unclassified Fallback Pool**: When a rule is deleted, its addresses are safely retained in the `unclassified_pool` and routed to `_Unclassified` rather than cluttering your Inbox.
- **Cross-Platform**: Runs in full native COM mode on Windows with Outlook Classic, and in simulated Mock Mode on Linux/macOS for development and testing.

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
│   ├── rules.yaml               # Active configuration (Rules, Groups, Stores)
│   └── backups/                 # Versioned automatic backups
├── core/
│   ├── models.py                # Data classes
│   ├── address_resolver.py      # X.500 to SMTP & email normalization
│   ├── yaml_manager.py          # YAML manager with versioned backups
│   ├── rule_splitter.py         # Quota protection & rule splitter
│   ├── outlook_client.py        # COM MAPI client & Linux mock client
│   └── sync_engine.py           # Synchronization & Specificity matching engine
├── gui/
│   ├── main_window.py           # Root window, tabs & quick sync
│   ├── triage_view.py           # 3-Pane Inbox inspector & rule assigner
│   ├── rule_manager_view.py     # Rule & Group CRUD and Excel importer
│   ├── rollover_view.py         # PST Year Rollover wizard & size monitor
│   └── dryrun_view.py           # Simulation engine (Inbox test run)
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── run_app.bat                  # Windows launch script
└── run_app.sh                   # Linux launch script
```

