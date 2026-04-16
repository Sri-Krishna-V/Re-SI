# Recurring Self Improvement (RSI)

Recurring Self Improvement (RSI) continuously upgrades your agent skills using a multi-agent system built with **Google ADK (Agent Development Kit)** and **Gemini**. Upload a skill, let the agents generate test scenarios and evaluation criteria, then run an RSI cycle where three specialized ADK agents collaborate to improve your skill.

![Recurring Self Improvement screenshot](https://github.com/user-attachments/assets/35a31f1a-398d-4797-a5d8-de538b4391e5)

## How It Works

This app implements an automated skill improvement loop inspired by Karpathy's autoresearch methodology, powered by a team of ADK agents:

1. **Upload**: Drop in your skill folder (following [agentskills.io](https://agentskills.io) spec)
2. **Configure**: The Executor agent generates test scenarios and evaluation criteria. Edit, add, or regenerate as needed
3. **RSI Cycle**: Three ADK agents collaborate - one executes and scores, one diagnoses failures, one applies fixes
4. **Results**: Download your RSI-improved skill with a detailed changelog

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFF7CC","primaryBorderColor":"#F9C74F","primaryTextColor":"#334155","secondaryColor":"#E0F2FE","tertiaryColor":"#FCE7F3","lineColor":"#94A3B8","fontFamily":"Trebuchet MS"}}}%%
sequenceDiagram
  autonumber
  participant U as User
  participant FE as Frontend Wizard
  participant API as FastAPI Backend
  participant AG as ADK Agent Team
  U->>FE: Upload skill and API key
  FE->>API: POST /api/upload + /api/analyze
  API-->>FE: scenarios and eval criteria
  U->>FE: Review and edit config
  FE->>API: POST /api/update-config
  FE->>API: POST /api/start/{session_id}
  API->>AG: Run RSI cycle
  loop every 3 seconds
    FE->>API: GET /api/status/{session_id}
    API-->>FE: experiments and status
  end
  API-->>FE: final result
  U->>FE: Download result package
  FE->>API: GET /api/download/{session_id}
```

### The ADK Agent Team

| Agent | Role | What It Does |
| ----- | ---- | ------------ |
| **Executor** | Skill Runner & Scorer | Executes the skill against test scenarios, scores outputs against evaluation criteria, and generates initial test scenarios during analysis |
| **Analyst** | Failure Diagnostician | Examines failed evaluations, identifies root causes, and recommends a mutation strategy. Uses Pydantic `output_schema` for guaranteed structured JSON |
| **Mutator** | Prompt Editor | Makes exactly ONE targeted change to the skill prompt based on the analyst's diagnosis. Uses Pydantic `output_schema` for guaranteed structured JSON |

### The RSI Cycle

- The **Executor** agent runs the skill against all test scenarios
- The **Executor** then scores each output against binary yes/no evaluation criteria
- The **Analyst** agent diagnoses failure patterns and picks a strategy (`add_example`, `add_constraint`, `restructure`, or `add_edge_case`)
- The **Mutator** agent applies ONE surgical fix to the skill prompt
- The **Executor** re-runs and re-scores the modified skill
- Changes are kept if the score improves, reverted if not
- Repeats until the target pass rate is reached or max rounds hit

## Architecture

```text
recurring-self-improvement-rsi/
├── backend/                 # FastAPI server + ADK RSI cycle engine
│   ├── app.py              # REST API endpoints + SSE streaming
│   ├── adk_optimizer.py    # Multi-agent optimizer (Executor, Analyst, Mutator)
│   └── requirements.txt
├── frontend/               # Next.js + React + Tailwind
│   ├── src/
│   │   ├── app/            # Main page + layout
│   │   └── components/     # Upload, Config, Running, Results steps
│   ├── package.json
│   └── *.config.ts
├── example_skills/         # Sample skills to test
│   ├── code-reviewer/
│   └── content-writer/
└── README.md
```

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#F7FEFF","primaryBorderColor":"#7DD3FC","primaryTextColor":"#334155","secondaryColor":"#ECFDF5","tertiaryColor":"#FFF7ED","lineColor":"#A8B5C2","fontFamily":"Trebuchet MS"}}}%%
flowchart LR
  subgraph FE[Frontend Next.js]
    P[page.tsx wizard]
    U[UploadStep]
    C[ConfigStep]
    R[RunningStep]
    O[ResultsStep]
    P --> U --> C --> R --> O
  end

  subgraph BE[Backend FastAPI]
    A1["/api/upload and /api/upload-files"]
    A2["/api/analyze and /api/regenerate"]
    A3["/api/update-config"]
    A4["/api/start, /api/status, /api/stop"]
    A5["/api/download"]
    S[(In-memory sessions)]
  end

  subgraph AG[Google ADK agents]
    EX[Executor]
    AN[Analyst]
    MU[Mutator]
  end

  U --> A1 --> S
  U --> A2 --> S
  C --> A3 --> S
  R --> A4 --> S
  O --> A5 --> S
  A4 --> EX
  EX --> AN --> MU --> EX

  classDef front fill:#E8F8FF,stroke:#67C5FF,color:#2C4F73;
  classDef back fill:#ECFFF3,stroke:#67D9A5,color:#2E5A44;
  classDef agent fill:#FFEAF4,stroke:#FF8BC2,color:#7A2E57;
  classDef store fill:#FFF8DB,stroke:#F7C75A,color:#6B4E12;
  class P,U,C,R,O front;
  class A1,A2,A3,A4,A5 back;
  class EX,AN,MU agent;
  class S store;
```

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, Google ADK, Pydantic
- **Frontend**: Next.js 15, React 19, Tailwind CSS v4, Recharts
- **AI**: Google ADK multi-agent system with Gemini (`gemini-3-flash-preview`) — structured output via `output_schema` on Analyst and Mutator agents
- **Real-time**: Server-Sent Events (SSE) for live RSI cycle progress

## Quick Start

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment (optional — the app will prompt for your API key in the UI)
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Run server
python app.py
# Server runs on http://localhost:8891
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
# App runs on http://localhost:3000
```

### Usage

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Open [http://localhost:3000](http://localhost:3000)
3. Upload a skill folder as a .zip file (or try an example)
4. Enter your Gemini API key
5. Review and edit the generated test scenarios and evaluation criteria
6. Click "Start RSI Cycle" and watch the agents collaborate to improve your skill
7. Download your RSI-improved skill when complete

## Skill Format

Skills follow the [agentskills.io](https://agentskills.io) specification:

```text
my-skill/
├── SKILL.md           # Required: YAML frontmatter + instructions
├── scripts/           # Optional: executable code
├── references/        # Optional: additional docs
└── assets/            # Optional: templates, resources
```

Example SKILL.md:

```markdown
---
name: my-skill
description: What this skill does and when to use it
license: MIT
metadata:
  author: your-name
  version: "1.0"
---

# My Skill

Your skill instructions here...
```

## Example Skills

Two example skills are included:

- **code-reviewer**: Reviews code for security, performance, and best practices
- **content-writer**: Writes marketing copy following style guidelines

Create a zip file from an example:

```bash
cd example_skills
zip -r code-reviewer.zip code-reviewer/
```

Then upload the zip in the app.

## How the Multi-Agent RSI Cycle Works

### 1. Analysis Phase

The **Executor** agent analyzes your skill and generates:

- 3-4 diverse test scenarios
- 4-6 binary evaluation criteria (yes/no questions)

You can edit, add, or remove scenarios and criteria before the RSI cycle begins.

### 2. Baseline Run

The **Executor** agent runs the skill against all scenarios and scores each output against all evaluation criteria. This establishes the starting score.

### 3. RSI Decision Loop

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#F7FEFF","primaryBorderColor":"#A7C7E7","lineColor":"#A8B5C2","fontFamily":"Trebuchet MS"}}}%%
flowchart TD
  B[Baseline score] --> X[Analyst diagnoses failures]
  X --> M[Mutator applies one targeted change]
  M --> S[Executor re-scores across scenarios and evals]
  S --> D{Score improved?}
  D -->|Yes| K[Keep mutation and update current skill]
  D -->|No| R[Revert mutation]
  K --> N{Target reached or max rounds hit?}
  R --> N
  N -->|No| X
  N -->|Yes| O[Finalize RSI-improved SKILL.md and changelog]

  classDef start fill:#EAF4FF,stroke:#7DBBFF,color:#2A4D70;
  classDef action fill:#ECFFF3,stroke:#86E3B0,color:#2A5A42;
  classDef decision fill:#FFFBE8,stroke:#FFD86B,color:#6A5213;
  classDef good fill:#E8FFF1,stroke:#66D38D,color:#1F5B3B;
  classDef bad fill:#FFF1F2,stroke:#FF9AA2,color:#7A3340;
  classDef finish fill:#FFF0FA,stroke:#FF9AD9,color:#7A2D63;
  class B start;
  class X,M,S action;
  class D,N decision;
  class K good;
  class R bad;
  class O finish;
```

For each round, the three agents collaborate:

1. **Executor** runs the skill against all test scenarios and scores the outputs
2. **Analyst** examines failures, identifies root cause, and selects a mutation strategy (returns structured JSON via `output_schema`)
3. **Mutator** applies ONE specific change to improve the skill in the current round (returns structured JSON via `output_schema`)
4. **Executor** re-runs and re-scores the modified skill
5. Score is compared - keep the change if improved, revert if not
6. Repeat until target pass rate or max rounds reached

### 4. Output

- RSI-improved SKILL.md with all successful changes applied
- Detailed changelog of what changed and why
- Performance comparison (baseline vs final)

## API Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `POST` | `/api/upload` | Upload skill zip file (max 10MB, text files only) |
| `POST` | `/api/upload-files` | Upload multiple files (folder upload) |
| `POST` | `/api/analyze` | Generate scenarios and evals (requires Gemini API key) |
| `POST` | `/api/regenerate` | Regenerate scenarios and evals |
| `POST` | `/api/update-config` | Save user's selected/edited config |
| `POST` | `/api/start/{session_id}` | Start RSI cycle |
| `GET` | `/api/stream/{session_id}` | SSE stream of RSI cycle progress |
| `POST` | `/api/stop/{session_id}` | Stop RSI cycle |
| `GET` | `/api/download/{session_id}` | Download RSI-improved skill |
| `GET` | `/api/examples` | List available example skills |
| `POST` | `/api/examples/{name}/load` | Load an example skill |
| `GET` | `/api/status/{session_id}` | Poll-based status endpoint |
| `GET` | `/health` | Health check |

## Configuration

### Backend

The Gemini API key is passed from the frontend with each request. Optionally set `GOOGLE_API_KEY` in `.env` for local development. Server runs on port **8891**.

Upload limits:

- **10MB** max total upload size
- **1MB** max per file
- **50** max files per upload
- Text files only (`.md`, `.txt`, `.json`, `.yaml`, `.py`, `.js`, `.ts`, etc.)

Sessions expire after **1 hour** automatically.

### Frontend

API key is entered in the UI, stored in component state (not persisted), and sent with each request. The key is passed to the backend which sets `GOOGLE_API_KEY` for ADK agent authentication.

### RSI Cycle Parameters

In `RunningStep.tsx`, adjust `max_rounds` (capped at 50):

```typescript
body: JSON.stringify({
  max_rounds: 20,  // Default: 20, max: 50
}),
```

In `adk_optimizer.py`, adjust the model:

```python
def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
```

## Development

### Backend Tests

```bash
cd backend
python -c "from adk_optimizer import SkillOptimizer; print('OK')"
```

### Frontend Build

```bash
cd frontend
npm run build
```

### Live Development

Both servers support hot reload. Edit code and see changes immediately.

## Based on Karpathy's Autoresearch

This tool applies Andrej Karpathy's autoresearch methodology (using LLMs to iteratively improve their own prompts) to agent skills. The key insight: rather than manually tweaking prompts, define success criteria and let the AI run recurring self improvement on itself - now powered by a team of specialized ADK agents.

Original concept: [https://github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch)
