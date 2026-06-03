# Sequence diagram — a conversational session

Each user message is one `run_turn`. The graph runs only the agents the intent needs; the
checkpointer persists state between turns. Two interrupt types are shown: prerequisite
confirmation and clarification HITL.

```mermaid
sequenceDiagram
    actor U as User
    participant CLI as CLI / Web
    participant O as orchestrator.run_turn
    participant G as LangGraph (+Postgres checkpointer)
    participant M as Manager
    participant A as Specialist agents
    participant DB as Neon Postgres

    U->>CLI: upload transcript (no task)
    CLI->>O: run_turn(cid, None)
    O->>G: ainvoke(seed)
    G->>M: intake
    M-->>O: capabilities offer
    O-->>CLI: TurnResult(message)
    CLI-->>U: "Here's what I can do…"

    U->>CLI: "draft a proposal"
    CLI->>O: run_turn(cid, "draft a proposal")
    O->>G: ainvoke({last_user_message})
    G->>M: classify_intent → {agents:[proposal]}
    G->>M: prerequisite_check → missing [requirement, planning]
    M-->>O: interrupt(confirmation)
    O-->>CLI: TurnResult(awaiting_confirmation)
    CLI-->>U: "Run requirement, planning first? (yes/no)"

    U->>CLI: "yes"
    CLI->>O: run_turn(cid, "yes")
    O->>G: ainvoke(Command(resume="yes"))
    G->>A: requirement → planning → proposal (dispatch loop)
    A->>DB: checkpoint after each agent
    Note over A: if clarification ran and a critical field<br/>was missing, it would interrupt here too
    G->>M: finalize (summary)
    M-->>O: assistant message
    O-->>CLI: TurnResult(message)
    CLI-->>U: "Done. I ran: requirement, planning, proposal."
```
