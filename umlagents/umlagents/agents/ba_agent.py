"""
Business Analyst Agent — Larman Inception Phase elicitation.

Drives a multi-phase consultant conversation to produce a complete, traceable
requirements YAML following Craig Larman ISBN 9780137488803.

Phases (Inception):
  1. Vision          — problem, users, goals, success criteria
  2. Actors          — primary users, secondary actors, external systems
  3. Use Cases       — actor goals (5-10 UC titles)
  4. UC Detail       — step-by-step flows, pre/post conditions, exceptions
  5. Domain Model    — key business concepts, glossary
  6. Non-Functional  — scale, performance, security, compliance
  7. Risks           — technical and business risks, assumptions
"""
import json
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import (
    AgentRole, Project, Actor, UseCase, ArtifactType, Artifact
)
from ..utils.validation import YAMLValidator, ValidationError


# ---------------------------------------------------------------------------
# Phase definitions — drives coverage assessment
# ---------------------------------------------------------------------------

PHASES = [
    {
        "id": "vision",
        "label": "Project Vision",
        "number": 1,
        "min_exchanges": 3,
        "coverage_keywords": ["name", "problem", "domain", "goal", "success", "user", "who"],
    },
    {
        "id": "actors",
        "label": "Actors & Stakeholders",
        "number": 2,
        "min_exchanges": 2,
        "coverage_keywords": ["actor", "user", "role", "system", "external", "staff", "customer"],
    },
    {
        "id": "use_cases",
        "label": "Use Cases",
        "number": 3,
        "min_exchanges": 3,
        "coverage_keywords": ["use case", "feature", "task", "action", "schedule", "create", "view", "manage"],
    },
    {
        "id": "uc_detail",
        "label": "Use Case Details",
        "number": 4,
        "min_exchanges": 4,
        "coverage_keywords": ["step", "flow", "error", "exception", "condition", "cancel", "fail", "invalid"],
    },
    {
        "id": "domain",
        "label": "Domain Model",
        "number": 5,
        "min_exchanges": 2,
        "coverage_keywords": ["concept", "entity", "term", "definition", "means", "called", "glossary"],
    },
    {
        "id": "nfr",
        "label": "Non-Functional Requirements",
        "number": 6,
        "min_exchanges": 2,
        "coverage_keywords": ["user", "scale", "performance", "security", "hipaa", "gdpr", "speed", "available"],
    },
    {
        "id": "risks",
        "label": "Risks & Assumptions",
        "number": 7,
        "min_exchanges": 1,
        "coverage_keywords": ["risk", "concern", "assumption", "depend", "challenge", "worry"],
    },
]

TOTAL_PHASES = len(PHASES)

YAML_TEMPLATE = """\
project:
  name: "..."
  domain: "..."
  description: "..."
  vision: "..."
  regulatory_frameworks: []

actors:
  - name: "..."
    description: "..."
    role: "PrimaryActor"
    goals:
      - "..."

use_cases:
  - id: "UC1"
    title: "..."
    actor: "..."
    priority: 1
    requirements_ref: "REQ-001"
    pre_conditions:
      - "..."
    success_scenario:
      - "1. Actor does X"
      - "2. System responds with Y"
      - "3. System validates input"
    extension_scenarios:
      - step_ref: 3
        condition: "If validation fails"
        steps:
          - "3a1. System displays error message"
          - "3a2. Actor corrects input and retries from step 3"
    post_conditions:
      - "..."
    uat_criteria:
      - "Given ... When ... Then ..."

domain_model:
  - concept: "..."
    definition: "..."
    relationships:
      - "..."

nfr:
  performance: "..."
  scale: "..."
  security: "..."
  availability: "..."
  compliance: "..."

risks:
  - risk: "..."
    impact: "High"
    mitigation: "..."

glossary:
  - term: "..."
    definition: "..."
"""


class BAAgent(BaseAgent):
    """
    BA Agent — Larman Inception Phase consultant.

    Web interactive mode (primary):
        web_get_next_question(history)  → next question or done signal
        web_synthesize_requirements(history) → complete YAML dict
        web_save_requirements(yaml_data) → project_id

    Other modes (kept for backward compatibility):
        run(context)  — yaml / prompt / skip modes
    """

    def __init__(
        self,
        db_session: Optional[Session] = None,
        project_id: Optional[int] = None,
    ):
        system_prompt = (
            "You are a senior business consultant and systems analyst following "
            "Craig Larman's OOA/OOD methodology (ISBN 9780137488803). "
            "You guide non-technical founders through the Inception phase, "
            "asking one focused question at a time, building on previous answers, "
            "and ensuring all seven inception areas are covered before synthesis."
        )
        super().__init__(
            name="BAAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.BA,
            db_session=db_session,
            project_id=project_id,
        )

    # =========================================================================
    # Web interactive API
    # =========================================================================

    def web_get_next_question(self, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Given conversation history, return the next consultant question.

        Args:
            history: List of {"question": str, "answer": str} dicts.

        Returns:
            {
                "question": str,
                "phase": str,          # phase id
                "phase_label": str,
                "phase_number": int,   # 1-7
                "total_phases": int,   # 7
                "done": bool
            }
            When done=True the dict also contains "summary": str.
        """
        if not history:
            return {
                "question": (
                    "Welcome! I'm your business consultant. I'll guide you through "
                    "defining your project requirements step by step, following a "
                    "proven methodology.\n\n"
                    "Let's begin: What is your project idea? Tell me the problem it "
                    "solves and who would benefit most from it."
                ),
                "phase": "vision",
                "phase_label": "Project Vision",
                "phase_number": 1,
                "total_phases": TOTAL_PHASES,
                "done": False,
            }

        prompt = self._build_next_question_prompt(history)
        response = self.call_deepseek(prompt, temperature=0.4, max_tokens=400)
        return self._parse_question_response(response, history)

    def web_synthesize_requirements(
        self, history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Synthesize the complete YAML requirements from the conversation history.

        Returns a parsed YAML dict ready to be saved to the database.
        """
        prompt = self._build_synthesis_prompt(history)
        response = self.call_deepseek(prompt, temperature=0.1, max_tokens=8192)
        return self._parse_yaml_response(response)

    def web_save_requirements(self, yaml_data: Dict[str, Any]) -> int:
        """
        Persist synthesized requirements to the database.

        Returns:
            project_id (int)
        """
        proj = yaml_data.get("project", {})
        project_id = self.create_or_load_project(
            name=proj.get("name", "Untitled Project"),
            domain=proj.get("domain", "General"),
            description=proj.get("description", ""),
            regulatory_frameworks=proj.get("regulatory_frameworks", []),
        )

        # Persist actors
        actors_map: Dict[str, Actor] = {}
        for a in yaml_data.get("actors", []):
            actor = Actor(
                project_id=project_id,
                name=a["name"],
                description=a.get("description", ""),
                role=a.get("role", "EndUser"),
            )
            self.db.add(actor)
            self.db.flush()
            actors_map[a["name"]] = actor

        # Persist use cases
        for i, uc in enumerate(yaml_data.get("use_cases", []), start=1):
            actor_name = uc.get("actor", "")
            actor_obj = actors_map.get(actor_name)
            use_case = UseCase(
                project_id=project_id,
                actor_id=actor_obj.id if actor_obj else None,
                uc_id=uc.get("id", f"UC{i}"),
                title=uc.get("title", f"Use Case {i}"),
                priority=uc.get("priority", 2),
                pre_conditions=uc.get("pre_conditions", []),
                success_scenario=uc.get("success_scenario", []),
                extension_scenarios=uc.get("extension_scenarios", []),
                post_conditions=uc.get("post_conditions", []),
                regulatory_requirements=uc.get("regulatory_requirements", []),
                uat_criteria=uc.get("uat_criteria", []),
            )
            self.db.add(use_case)

        self.db.commit()

        # Save YAML artifact
        yaml_content = yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True)
        self.save_artifact(
            filepath=f"output/project_{project_id}/requirements.yaml",
            content=yaml_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={
                "source": "web_interactive",
                "actor_count": len(yaml_data.get("actors", [])),
                "use_case_count": len(yaml_data.get("use_cases", [])),
            },
        )

        # Save human-readable Markdown specification
        md_content = self._generate_requirements_md(yaml_data)
        self.save_artifact(
            filepath=f"output/project_{project_id}/requirements.md",
            content=md_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={
                "source": "web_interactive",
                "format": "markdown",
            },
        )

        self.log_activity(
            action="requirements_elicited",
            details={
                "project_id": project_id,
                "actor_count": len(yaml_data.get("actors", [])),
                "use_case_count": len(yaml_data.get("use_cases", [])),
                "method": "web_interactive_larman",
            },
        )
        return project_id

    # =========================================================================
    # Prompt builders
    # =========================================================================

    def _build_next_question_prompt(self, history: List[Dict[str, str]]) -> str:
        history_text = "\n\n".join(
            f"Consultant: {item['question']}\nFounder: {item['answer']}"
            for item in history
        )
        phase_status = self._phase_coverage_summary(history)

        return (
            "You are a senior business consultant conducting a Larman Inception Phase "
            "requirements interview with a non-technical founder.\n\n"
            f"CONVERSATION SO FAR ({len(history)} exchanges):\n"
            f"{history_text}\n\n"
            f"PHASE COVERAGE:\n{phase_status}\n\n"
            "PHASES TO COVER (in order, with minimum exchanges each):\n"
            + "\n".join(
                f"  {p['number']}. {p['label']} (min {p['min_exchanges']} exchanges)"
                for p in PHASES
            )
            + "\n\n"
            "RULES:\n"
            "- Ask ONE focused question at a time\n"
            "- Be conversational — this person is NOT technical\n"
            "- Build directly on their previous answers\n"
            "- For Use Case Detail: walk through each use case one by one\n"
            "- If a phase has enough info, advance to the next phase\n"
            "- When ALL 7 phases have their minimum exchanges, set done=true\n\n"
            "RESPOND WITH VALID JSON ONLY — no explanation outside the JSON:\n"
            '{"question": "...", "phase": "<phase_id>", "phase_label": "...", '
            '"phase_number": <1-7>, "done": false}\n'
            "OR when complete:\n"
            '{"done": true, "summary": "one sentence describing the project"}'
        )

    def _build_synthesis_prompt(self, history: List[Dict[str, str]]) -> str:
        history_text = "\n\n".join(
            f"Q: {item['question']}\nA: {item['answer']}"
            for item in history
        )
        return (
            "You are a senior business analyst. Based on this requirements interview, "
            "generate a complete, professional YAML specification following Craig Larman's "
            "OOA/OOD methodology.\n\n"
            f"INTERVIEW TRANSCRIPT:\n{history_text}\n\n"
            "STRICT RULES — every rule is mandatory:\n"
            "1. Every field must have a REAL, SPECIFIC value — NO 'To be defined'\n"
            "2. success_scenario steps MUST be numbered: '1. Actor does X', '2. System does Y', etc.\n"
            "3. Each extension_scenario MUST include step_ref (integer) — the success_scenario step number "
            "where the branch occurs. Example: step_ref: 3 means 'branches from step 3'.\n"
            "4. Extension steps MUST be numbered using Larman notation: '3a1. ...', '3a2. ...', "
            "where '3' is the step_ref and 'a', 'b' distinguish multiple extensions on the same step.\n"
            "5. uat_criteria must use Given/When/Then format\n"
            "6. requirements_ref must be unique per use case (REQ-001, REQ-002 ...)\n"
            "7. Infer reasonable values from context when not explicitly stated\n"
            "8. Include traceability: each use case links to actor and requirements_ref\n\n"
            f"YAML TEMPLATE TO FOLLOW:\n{YAML_TEMPLATE}\n\n"
            "Reply with a single ```yaml ... ``` code block. Nothing else."
        )

    # =========================================================================
    # Response parsers
    # =========================================================================

    def _parse_question_response(
        self, response: str, history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Parse LLM JSON response into a question dict."""
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
        # Extract first JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if data.get("done"):
                    return {
                        "done": True,
                        "summary": data.get("summary", "Requirements captured."),
                        "phase": "complete",
                        "phase_label": "Complete",
                        "phase_number": TOTAL_PHASES,
                        "total_phases": TOTAL_PHASES,
                    }
                return {
                    "question": data.get("question", "Can you tell me more?"),
                    "phase": data.get("phase", "vision"),
                    "phase_label": data.get("phase_label", ""),
                    "phase_number": int(data.get("phase_number", 1)),
                    "total_phases": TOTAL_PHASES,
                    "done": False,
                }
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: treat response as a plain question
        return {
            "question": response.strip(),
            "phase": self._current_phase(history),
            "phase_label": self._current_phase_label(history),
            "phase_number": self._current_phase_number(history),
            "total_phases": TOTAL_PHASES,
            "done": False,
        }

    def _parse_yaml_response(self, response: str) -> Dict[str, Any]:
        """Extract and parse YAML from LLM response."""
        # Try fenced block first
        match = re.search(r"```(?:yaml)?\s*\n(.*?)```", response, re.DOTALL | re.IGNORECASE)
        yaml_text = match.group(1) if match else response

        try:
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass

        # Return minimal valid structure on parse failure
        return {
            "project": {
                "name": "Untitled Project",
                "domain": "General",
                "description": "Requirements could not be parsed.",
                "vision": "",
                "regulatory_frameworks": [],
            },
            "actors": [],
            "use_cases": [],
            "domain_model": [],
            "nfr": {},
            "risks": [],
            "glossary": [],
        }

    # =========================================================================
    # Phase coverage helpers
    # =========================================================================

    def _phase_coverage_summary(self, history: List[Dict[str, str]]) -> str:
        all_text = " ".join(
            (item["question"] + " " + item["answer"]).lower() for item in history
        )
        lines = []
        for p in PHASES:
            hits = sum(1 for kw in p["coverage_keywords"] if kw in all_text)
            covered = hits >= 2
            status = "[covered]" if covered else "[pending]"
            lines.append(f"  Phase {p['number']} {p['label']}: {status}")
        return "\n".join(lines)

    def _current_phase(self, history: List[Dict[str, str]]) -> str:
        all_text = " ".join(
            (item["question"] + " " + item["answer"]).lower() for item in history
        )
        for p in PHASES:
            hits = sum(1 for kw in p["coverage_keywords"] if kw in all_text)
            if hits < 2:
                return p["id"]
        return PHASES[-1]["id"]

    def _current_phase_label(self, history: List[Dict[str, str]]) -> str:
        pid = self._current_phase(history)
        return next((p["label"] for p in PHASES if p["id"] == pid), "")

    def _current_phase_number(self, history: List[Dict[str, str]]) -> int:
        pid = self._current_phase(history)
        return next((p["number"] for p in PHASES if p["id"] == pid), 1)

    # =========================================================================
    # Requirements document generator
    # =========================================================================

    def _generate_requirements_md(self, yaml_data: Dict[str, Any]) -> str:
        """Generate a human-readable requirements specification from YAML data."""
        from datetime import datetime

        proj   = yaml_data.get("project", {})
        actors = yaml_data.get("actors", [])
        ucs    = yaml_data.get("use_cases", [])
        domain = yaml_data.get("domain_model", [])
        nfr    = yaml_data.get("nfr", {})
        risks  = yaml_data.get("risks", [])
        gloss  = yaml_data.get("glossary", [])
        reg    = proj.get("regulatory_frameworks", [])

        lines: List[str] = []

        # ── Header ──────────────────────────────────────────────────────────
        lines += [
            f"# {proj.get('name', 'Untitled Project')} — Requirements Specification",
            "",
            f"**Domain:** {proj.get('domain', '')}  ",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d')}  ",
            f"**Methodology:** Craig Larman OOA/OOD Inception Phase (ISBN 9780137488803)  ",
        ]
        if reg:
            lines.append(f"**Regulatory frameworks:** {', '.join(reg)}  ")
        lines += ["", "---", ""]

        # ── Vision ───────────────────────────────────────────────────────────
        lines += ["## 1. Vision", ""]
        lines.append(proj.get("vision") or proj.get("description") or "_No vision statement provided._")
        lines += ["", "---", ""]

        # ── Actors ───────────────────────────────────────────────────────────
        lines += ["## 2. Actors & Stakeholders", ""]
        if actors:
            lines += ["| Actor | Role | Description | Goals |", "|-------|------|-------------|-------|"]
            for a in actors:
                goals = "; ".join(a.get("goals", [])) or "—"
                lines.append(f"| **{a.get('name','')}** | {a.get('role','')} | {a.get('description','')} | {goals} |")
        else:
            lines.append("_No actors defined._")
        lines += ["", "---", ""]

        # ── Use Cases ────────────────────────────────────────────────────────
        lines += ["## 3. Use Cases", ""]
        for uc in ucs:
            lines += [
                f"### {uc.get('id','UC?')}: {uc.get('title','')}",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| **Actor** | {uc.get('actor', '—')} |",
                f"| **Priority** | {uc.get('priority', '—')} |",
                f"| **Requirement ref** | {uc.get('requirements_ref', '—')} |",
                "",
            ]

            pre = uc.get("pre_conditions", [])
            if pre:
                lines.append("**Pre-conditions**")
                lines += [f"- {p}" for p in pre]
                lines.append("")

            # Numbered success scenario steps
            raw_steps = uc.get("success_scenario", [])
            if raw_steps:
                lines.append("**Main success scenario**")
                lines.append("")
                for i, s in enumerate(raw_steps, start=1):
                    # Strip any existing leading number so we don't double-number
                    import re as _re
                    text = _re.sub(r"^\d+\.\s*", "", str(s))
                    lines.append(f"{i}. {text}")
                lines.append("")

            # Extensions in Larman notation: step_ref + alphabetic suffix
            exts = uc.get("extension_scenarios", [])
            if exts:
                lines.append("**Extensions**")
                lines.append("")
                # Group extensions by step_ref so multiple extensions on same
                # step get letters a, b, c ...
                from collections import defaultdict
                by_step: dict = defaultdict(list)
                unlinked = []
                for ext in exts:
                    ref = ext.get("step_ref")
                    if ref is not None:
                        by_step[int(ref)].append(ext)
                    else:
                        unlinked.append(ext)

                for step_num in sorted(by_step.keys()):
                    for letter_idx, ext in enumerate(by_step[step_num]):
                        letter = chr(ord('a') + letter_idx)
                        prefix = f"{step_num}{letter}"
                        lines.append(f"**{prefix}.** {ext.get('condition', '')}:")
                        for sub_i, step in enumerate(ext.get("steps", []), start=1):
                            # Strip existing Larman prefix if LLM already added it
                            text = _re.sub(r"^\d+[a-z]\d+\.\s*", "", str(step))
                            lines.append(f"- {prefix}{sub_i}. {text}")
                        lines.append("")

                # Unlinked extensions (no step_ref — older YAML format)
                for ext_i, ext in enumerate(unlinked):
                    lines.append(f"- *{ext.get('condition', '')}*")
                    for step in ext.get("steps", []):
                        lines.append(f"  - {step}")
                lines.append("")

            post = uc.get("post_conditions", [])
            if post:
                lines.append("**Post-conditions**")
                lines += [f"- {p}" for p in post]
                lines.append("")

            uat = uc.get("uat_criteria", [])
            if uat:
                lines.append("**UAT acceptance criteria**")
                lines += [f"- {u}" for u in uat]
                lines.append("")

            lines.append("---")
            lines.append("")

        # ── Domain Model ─────────────────────────────────────────────────────
        if domain:
            lines += ["## 4. Domain Model", ""]
            lines += ["| Concept | Definition | Relationships |", "|---------|------------|---------------|"]
            for d in domain:
                rels = "; ".join(d.get("relationships", [])) or "—"
                lines.append(f"| **{d.get('concept','')}** | {d.get('definition','')} | {rels} |")
            lines += ["", "---", ""]

        # ── NFRs ─────────────────────────────────────────────────────────────
        if nfr:
            lines += ["## 5. Non-Functional Requirements", ""]
            labels = {
                "performance": "Performance", "scale": "Scale / Capacity",
                "security": "Security", "availability": "Availability",
                "compliance": "Compliance",
            }
            for key, label in labels.items():
                val = nfr.get(key)
                if val:
                    lines.append(f"**{label}:** {val}  ")
            lines += ["", "---", ""]

        # ── Risks ────────────────────────────────────────────────────────────
        if risks:
            lines += ["## 6. Risks & Assumptions", ""]
            lines += ["| Risk | Impact | Mitigation |", "|------|--------|------------|"]
            for r in risks:
                lines.append(f"| {r.get('risk','')} | {r.get('impact','')} | {r.get('mitigation','')} |")
            lines += ["", "---", ""]

        # ── Glossary ─────────────────────────────────────────────────────────
        if gloss:
            lines += ["## 7. Glossary", ""]
            for g in gloss:
                lines.append(f"**{g.get('term','')}** — {g.get('definition','')}")
                lines.append("")

        lines += [
            "---",
            "",
            "_Generated by UMLAgents using Craig Larman's Inception Phase methodology._",
        ]

        return "\n".join(lines)

    # =========================================================================
    # run() — backward-compatible entry point
    # =========================================================================

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        mode = self._determine_mode(context)
        if mode == "yaml":
            return self._run_yaml_mode(context)
        elif mode == "prompt":
            return self._run_prompt_mode(context)
        elif mode == "skip":
            return self._run_skip_mode(context)
        else:
            raise ValueError(
                "Interactive BA must be started from the web UI. "
                "Go to Requirements → Start Interactive Session."
            )

    def _determine_mode(self, context: Dict[str, Any]) -> str:
        if context.get("skip_existing", False) and self.project_id:
            existing = self.db.query(UseCase).filter(
                UseCase.project_id == self.project_id
            ).count()
            if existing > 0:
                print(f"[{self.name}] Skipping BA — {existing} use cases already exist")
                return "skip"
            raise ValueError(
                f"Project {self.project_id} has no use cases. "
                "Start an Interactive Session in the Requirements tab first."
            )
        if "yaml_path" in context:
            return "yaml"
        if "prompt" in context or "project_description" in context:
            return "prompt"
        return "interactive"

    def _run_skip_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.project_id:
            context["project_id"] = self.project_id
        return context

    def _run_yaml_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        yaml_path = context["yaml_path"]
        print(f"[{self.name}] Loading YAML: {yaml_path}")
        try:
            yaml_data = YAMLValidator.validate_file(Path(yaml_path))
        except ValidationError as e:
            print(f"[{self.name}] YAML validation failed: {e.message}")
            raise

        project_id = self.create_or_load_project(
            name=yaml_data["project"]["name"],
            domain=yaml_data["project"]["domain"],
            description=yaml_data["project"]["description"],
            regulatory_frameworks=yaml_data["project"].get("regulatory_frameworks", []),
        )
        actors = []
        for a in yaml_data.get("actors", []):
            actor = Actor(
                project_id=project_id,
                name=a["name"],
                description=a["description"],
                role=a.get("role", "EndUser"),
            )
            self.db.add(actor)
            actors.append(actor)
        self.db.commit()

        for uc_data in yaml_data.get("use_cases", []):
            actor_id = None
            if "actor" in uc_data:
                actor = next((a for a in actors if a.name == uc_data["actor"]), None)
                if actor:
                    actor_id = actor.id
            use_case = UseCase(
                project_id=project_id,
                actor_id=actor_id,
                uc_id=uc_data["id"],
                title=uc_data["title"],
                priority=uc_data.get("priority", 2),
                pre_conditions=uc_data.get("pre_conditions", []),
                success_scenario=uc_data.get("success_scenario", []),
                extension_scenarios=uc_data.get("extension_scenarios", []),
                post_conditions=uc_data.get("post_conditions", []),
                regulatory_requirements=uc_data.get("regulatory_requirements", []),
                uat_criteria=uc_data.get("uat_criteria", []),
            )
            self.db.add(use_case)
        self.db.commit()

        yaml_content = yaml.dump(yaml_data, default_flow_style=False)
        self.save_artifact(
            filepath=f"output/project_{project_id}/requirements.yaml",
            content=yaml_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={"source": "yaml_file", "yaml_path": yaml_path},
        )

        md_content = self._generate_requirements_md(yaml_data)
        self.save_artifact(
            filepath=f"output/project_{project_id}/requirements.md",
            content=md_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={"source": "yaml_file", "format": "markdown"},
        )

        context["project_id"] = project_id
        context["requirements_yaml"] = yaml_data
        print(f"[{self.name}] Loaded {len(actors)} actors, {len(yaml_data.get('use_cases', []))} use cases")
        return context

    def _run_prompt_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt_text = context.get("prompt") or context.get("project_description", "")
        print(f"[{self.name}] Generating requirements from prompt")
        enhanced = (
            "Analyse the following project description using Craig Larman's "
            "OOA/OOD Inception phase methodology and produce a complete YAML "
            f"requirements specification.\n\nProject description:\n{prompt_text}\n\n"
            f"YAML TEMPLATE:\n{YAML_TEMPLATE}\n\n"
            "Reply with a single ```yaml ... ``` block. No explanation."
        )
        response = self.call_deepseek(enhanced, max_tokens=8192)
        yaml_data = self._parse_yaml_response(response)
        project_id = self.web_save_requirements(yaml_data)
        context["project_id"] = project_id
        context["requirements_yaml"] = yaml_data
        return context
