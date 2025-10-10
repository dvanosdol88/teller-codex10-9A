<!--
========================================================================
SYNC IMPACT REPORT - Constitution Update
========================================================================
Version Change: INITIAL → 1.0.0
Change Type: Initial Constitution Creation
Date: 2025-10-08

Modified Principles:
- INITIAL: All principles created from template

Added Sections:
- I. Specification-First Development
- II. User-Centric Testing
- III. Independent User Stories
- IV. Technology Agnostic Design
- V. Iterative Refinement
- Development Workflow
- Quality Gates

Removed Sections:
- None (initial creation)

Template Consistency Status:
- ✅ .specify/templates/plan-template.md - Constitution Check section compatible
- ✅ .specify/templates/spec-template.md - User story structure aligns with Principle III
- ✅ .specify/templates/tasks-template.md - User story organization aligns with Principle III
- ✅ .specify/templates/checklist-template.md - No constitution-specific references
- ✅ .specify/templates/agent-file-template.md - No constitution-specific references

Follow-up TODOs:
- None - all placeholders filled

Notes:
- This is the initial constitution for the New Start Teller project
- Principles aligned with Specify framework best practices
- All templates reviewed for consistency
========================================================================
-->

# New Start Teller Constitution

## Core Principles

### I. Specification-First Development

All features MUST begin with a clear specification that defines:
- User scenarios with acceptance criteria in Given/When/Then format
- Functional requirements with FR-XXX identifiers
- Success criteria with measurable outcomes
- Technology-agnostic design without implementation details

**Rationale**: Separating "what" from "how" enables better design decisions, clearer communication, and easier validation of requirements before implementation begins.

### II. User-Centric Testing

Every feature specification MUST include:
- Prioritized user stories/journeys (P1, P2, P3...)
- Independently testable scenarios for each story
- Edge cases and boundary conditions
- Clear acceptance criteria

Tests are OPTIONAL for implementation unless explicitly requested in the specification.

**Rationale**: User-focused testing ensures features deliver actual value and can be validated independently, even when technical tests are not implemented.

### III. Independent User Stories

Each user story MUST be:
- Independently implementable without requiring other stories
- Independently testable with clear validation criteria
- Able to deliver value as a standalone increment
- Prioritized (P1 = MVP, P2 = enhancement, P3+ = nice-to-have)

**Rationale**: Independent stories enable incremental delivery, parallel development, and MVP-first approach. If implementing only P1 delivers value, the feature is properly decomposed.

### IV. Technology Agnostic Design

Specifications and plans MUST:
- Avoid coupling to specific technologies unless justified
- Use [NEEDS CLARIFICATION] for uncertain technical decisions
- Document technology choices with rationale in implementation plans
- Separate business logic from infrastructure concerns

**Rationale**: Technology-agnostic design preserves flexibility, enables better technology choices, and prevents premature optimization.

### V. Iterative Refinement

The development workflow MUST support:
- Clarification of underspecified requirements via `/speckit.clarify`
- Progressive elaboration from spec → plan → tasks
- Cross-artifact consistency analysis via `/speckit.analyze`
- Continuous validation and refinement at each phase

**Rationale**: Complex features emerge through iteration. Early-phase mistakes are cheaper to fix than late-phase bugs.

## Development Workflow

### Phase Progression

1. **Specification** (`/speckit.specify`): Capture WHAT and WHY
   - User scenarios, functional requirements, success criteria
   - Technology-agnostic, focused on user value

2. **Clarification** (`/speckit.clarify`): Resolve ambiguities
   - Identify underspecified areas with targeted questions
   - Encode answers back into specification

3. **Planning** (`/speckit.plan`): Define HOW
   - Technical research, architecture decisions, data models
   - Project structure, contracts, quickstart guide

4. **Task Generation** (`/speckit.tasks`): Actionable implementation
   - Dependency-ordered tasks organized by user story
   - Foundation phase → User stories (P1, P2, P3...) → Polish
   - Each story checkpoint validates independent functionality

5. **Analysis** (`/speckit.analyze`): Quality assurance
   - Cross-artifact consistency checks
   - Requirements traceability
   - Completeness validation

6. **Implementation** (`/speckit.implement`): Execute tasks
   - Process tasks in dependency order
   - Validate checkpoints for each user story

### Mandatory Gates

- **Pre-Planning**: Specification MUST be complete and clarified
- **Pre-Tasks**: Implementation plan MUST pass Constitution Check
- **Pre-Implementation**: Tasks MUST be validated for dependencies and completeness
- **Post-Implementation**: Analysis MUST confirm cross-artifact consistency

## Quality Gates

### Specification Quality

- ✅ All user stories have priority assignments (P1, P2, P3...)
- ✅ Each user story is independently testable
- ✅ Functional requirements use FR-XXX identifiers
- ✅ Success criteria are measurable
- ✅ Edge cases documented

### Planning Quality

- ✅ Technical context specifies language, framework, testing approach
- ✅ Project structure matches project type (single/web/mobile)
- ✅ Data models defined for data-centric features
- ✅ API contracts documented for service features
- ✅ Constitution Check passes or violations justified

### Task Quality

- ✅ Tasks organized by user story for independent implementation
- ✅ Foundation phase identified and separated from story work
- ✅ Dependencies clearly marked, parallelizable tasks tagged [P]
- ✅ Each user story has checkpoint validation
- ✅ File paths are specific and accurate

### Implementation Quality

- ✅ Tests written BEFORE implementation (if tests requested)
- ✅ Each user story validated independently at its checkpoint
- ✅ Code follows conventions from agent-file-template.md
- ✅ Commits reference feature branch and task IDs

## Governance

### Amendment Process

1. Propose amendment with rationale and impact analysis
2. Update constitution with version bump (MAJOR.MINOR.PATCH):
   - **MAJOR**: Backward incompatible principle removal/redefinition
   - **MINOR**: New principle or materially expanded guidance
   - **PATCH**: Clarifications, wording, non-semantic refinements
3. Validate all templates for consistency
4. Update Sync Impact Report
5. Commit with message: `docs: amend constitution to vX.Y.Z (description)`

### Compliance Review

- All `/speckit.*` commands MUST verify compliance with this constitution
- Violations MUST be documented with justification in relevant artifacts
- Unjustified violations block progression to next phase
- Constitution supersedes all other practices and templates

### Version Control

- Constitution version tracked in this file's footer
- Ratification date never changes (original adoption)
- Last amended date updates with each modification
- Sync Impact Report prepended as HTML comment after each update

**Version**: 1.0.0 | **Ratified**: 2025-10-08 | **Last Amended**: 2025-10-08
