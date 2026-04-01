### My AI Assistant v2.0 - Clean Architecture

A global, production-ready AI Assistant for ERPNext with:
- **Clean Architecture** - Modular services with separation of concerns
- **Global Search** - Answers any question about your ERPNext data
- **Document Scanning** - Upload images to auto-create SI, PI, SO, PO
- **Dynamic Doctypes** - Automatically discovers and works with custom doctypes
- **Multi-Site Safe** - Site-aware configuration, works across multiple live sites

### Architecture

```
my_ai_assistant/
├── assistant.py             # Main orchestrator
├── api.py                   # API endpoints
├── config/settings.py       # Site-safe configuration
├── services/
│   ├── ai_service.py        # AI model interactions
│   ├── data_service.py      # Safe data retrieval
│   ├── document_service.py  # Document creation
│   ├── doctype_service.py   # Dynamic doctype discovery
│   ├── entity_service.py    # Entity extraction
│   └── image_service.py     # Document image processing
└── utils/gstin_helper.py    # GSTIN utilities
```

### Setup Instructions

1. **Configure API Key:**
```bash
bench --site skydot set-config vertex_api_key YOUR_GEMINI_API_KEY
```

2. **Install App:**
```bash
bench --site skydot install-app my_ai_assistant
bench --site skydot migrate
```

3. **Access AI Chat:**
Navigate to **AI Business Assistant** in ERPNext sidebar or go to `/app/ai-chat`

### Features

**Global Search Capability - Ask ANY question:**
- "How many customers/suppliers/items?"
- "Total revenue this month/year"
- "Show all overdue invoices"
- "Customer ABC billing summary"
- "Stock of Item XYZ"
- "Show SINV-2024-00001"

**Document Image Processing:**
- Upload Sales Invoice → Creates Sales Invoice draft
- Upload Purchase Bill → Creates Purchase Invoice draft
- Upload Sales Order → Creates Sales Order draft
- Upload Purchase Order → Creates Purchase Order draft

**Dynamic Doctypes:**
- Automatically discovers custom doctypes
- Works with any new doctype you create
- Auto-extracts field structure

### API Endpoints

```javascript
// Ask AI
frappe.call({
    method: 'my_ai_assistant.api.get_ai_response',
    args: { prompt: 'How many customers?' },
    callback: (r) => console.log(r.message)
});

// Process Document Image
frappe.call({
    method: 'my_ai_assistant.api.process_document_image_api',
    args: { image_data: base64_string, document_type: 'auto' },
    callback: (r) => console.log(r.message)
});

// Discover Doctypes
frappe.call({
    method: 'my_ai_assistant.api.get_doctypes_list',
    args: { category: 'transactions' },
    callback: (r) => console.log(r.message)
});
```

### Multi-Site Configuration

Each site has independent settings via `site_config.json`:
```json
{
    "vertex_api_key": "YOUR_KEY",
    "ai_model": "gemini-2.5-flash",
    "ai_enable_image_processing": 1
}
```

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app my_ai_assistant
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/my_ai_assistant
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

### License

mit
