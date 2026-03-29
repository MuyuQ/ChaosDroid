# ChaosDroid

Android fault injection testing and recovery verification platform.

## Installation

```bash
pip install chaosdroid
```

## Quick Start

```bash
# Initialize database and directories
chaosdroid init

# Start web service
chaosdroid serve --port 8000

# List scenarios
chaosdroid scenario list

# Run a scenario
chaosdroid run <scenario-id> --device <serial> --mode mock
```

## Features

- Support standardized fault injection scenarios
- Support fault injection at specified stages
- Support real and mock device modes
- Support execution validation and observation collection
- Support recovery actions and result judgment
- Support Markdown/HTML report generation