# Agent flow map (intent-driven)

One graph invocation = one user turn. The Manager classifies intent and only the needed agents
run; missing prerequisites are confirmed with the user first.

```mermaid
stateDiagram-v2
    [*] --> Intake
    Intake --> CapabilitiesOffer: no task given yet
    CapabilitiesOffer --> [*]: show menu, wait for next turn
    Intake --> IntentClassifier: has instruction
    IntentClassifier --> PrerequisiteCheck

    PrerequisiteCheck --> AskUser: prerequisites missing
    AskUser --> PrerequisiteCheck: user answers (yes/no)
    PrerequisiteCheck --> Dispatch: queue ready
    PrerequisiteCheck --> Finalize: unmappable / declined

    state Dispatch {
        [*] --> NextAgent
        NextAgent --> RunAgent
        RunAgent --> ClarifyHITL: clarification finds a critical gap
        ClarifyHITL --> RunAgent: user answers
        RunAgent --> NextAgent: more in queue
        RunAgent --> [*]: queue empty
    }

    Dispatch --> Finalize
    Finalize --> [*]: assistant summary, control back to user
```

Agents reachable in `Dispatch` (run only when the intent needs them, in dependency order):
`transcription` (audio only), `requirement`, `clarification`, `planning`, `task_generation`,
`risk`, `proposal`, `validator`, `executor`.
