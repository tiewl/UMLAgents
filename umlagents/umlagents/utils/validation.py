"""
Validation utilities for UMLAgents.
Provides comprehensive validation for YAML specifications, CLI arguments, and data integrity.
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
import re


class ValidationError(Exception):
    """Raised when validation fails."""
    def __init__(self, message: str, field: str = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)


class YAMLValidator:
    """Validate YAML specifications against UMLAgents schema."""
    
    # Schema definition (based on umlagents-schema-v0.1.yaml)
    SCHEMA = {
        "project": {
            "required": ["name", "domain", "description"],
            "optional": ["regulatory_frameworks"],
            "types": {
                "name": str,
                "domain": str,
                "description": str,
                "regulatory_frameworks": list
            }
        },
        "actors": {
            "required": ["name", "description"],
            "optional": ["role"],
            "types": {
                "name": str,
                "description": str,
                "role": str
            },
            "defaults": {"role": "EndUser"}
        },
        "use_cases": {
            "required": ["id", "title", "actor", "priority", 
                        "pre_conditions", "success_scenario", "post_conditions"],
            "optional": ["extension_scenarios", "regulatory_requirements", "uat_criteria"],
            "types": {
                "id": str,
                "title": str,
                "actor": str,
                "priority": int,
                "pre_conditions": list,
                "success_scenario": list,
                "extension_scenarios": list,
                "post_conditions": list,
                "regulatory_requirements": list,
                "uat_criteria": list
            },
            "constraints": {
                "priority": {"min": 1, "max": 3},
                "id": {"pattern": r"^(UC\d+|[\w\-]+)$"}  # UC1 or AUTH-001 format
            }
        }
    }
    
    @classmethod
    def validate_file(cls, yaml_path: Path, collect_all_errors: bool = False) -> Dict[str, Any]:
        """
        Validate a YAML file against the schema.
        Returns parsed YAML data if valid.
        Raises ValidationError with detailed message if invalid.
        
        Args:
            yaml_path: Path to YAML file
            collect_all_errors: If True, collect all errors before raising
                              (only raises first error if False)
        """
        errors = []
        
        # Check file exists and is readable
        if not yaml_path.exists():
            raise ValidationError(f"YAML file not found: {yaml_path}")
        if not yaml_path.is_file():
            raise ValidationError(f"Path is not a file: {yaml_path}")
        
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except IOError as e:
            raise ValidationError(f"Cannot read YAML file: {e}")
        
        # Parse YAML
        try:
            yaml_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML syntax: {e}")
        
        # Validate structure
        try:
            cls._validate_structure(yaml_data, collect_all_errors)
        except ValidationError as e:
            if collect_all_errors:
                errors.append(e)
            else:
                raise
        
        # Validate cross-references
        try:
            cls._validate_references(yaml_data)
        except ValidationError as e:
            if collect_all_errors:
                errors.append(e)
            else:
                raise
        
        # If collecting all errors and we have errors, raise the first one
        # (in a real implementation, we'd create a MultiValidationError)
        if collect_all_errors and errors:
            # For now, raise the first error
            raise errors[0]
        
        return yaml_data
    
    @classmethod
    def _validate_structure(cls, data: Dict[str, Any], collect_all_errors: bool = False) -> None:
        """Validate top-level structure and each section."""
        # Check required top-level sections
        if "project" not in data:
            raise ValidationError("Missing required section: 'project'")
        
        # Validate project section
        cls._validate_section(data["project"], "project", cls.SCHEMA["project"], collect_all_errors)
        
        # Validate actors (optional but if present must follow schema)
        if "actors" in data:
            if not isinstance(data["actors"], list):
                raise ValidationError("'actors' must be a list", field="actors")
            
            actor_names = set()
            for i, actor in enumerate(data["actors"]):
                cls._validate_section(actor, f"actors[{i}]", cls.SCHEMA["actors"], collect_all_errors)
                
                # Check for duplicate actor names
                actor_name = actor.get("name")
                if actor_name in actor_names:
                    raise ValidationError(
                        f"Duplicate actor name: '{actor_name}'", 
                        field=f"actors[{i}].name"
                    )
                actor_names.add(actor_name)
        
        # Validate use_cases (optional but if present must follow schema)
        if "use_cases" in data:
            if not isinstance(data["use_cases"], list):
                raise ValidationError("'use_cases' must be a list", field="use_cases")
            
            uc_ids = set()
            for i, uc in enumerate(data["use_cases"]):
                cls._validate_section(uc, f"use_cases[{i}]", cls.SCHEMA["use_cases"], collect_all_errors)
                
                # Check for duplicate use case IDs
                uc_id = uc.get("id")
                if uc_id in uc_ids:
                    raise ValidationError(
                        f"Duplicate use case ID: '{uc_id}'", 
                        field=f"use_cases[{i}].id"
                    )
                uc_ids.add(uc_id)
    
    @classmethod
    def _validate_section(cls, section: Dict[str, Any], section_path: str, schema: Dict, 
                         collect_all_errors: bool = False) -> None:
        """Validate a single section (project, actor, or use case)."""
        errors = []
        
        # Check required fields
        for field in schema["required"]:
            if field not in section:
                errors.append(ValidationError(
                    f"Missing required field: '{field}'",
                    field=f"{section_path}.{field}"
                ))
        
        # Check field types
        for field, value in section.items():
            if field in schema["types"]:
                expected_type = schema["types"][field]
                if not isinstance(value, expected_type):
                    errors.append(ValidationError(
                        f"Field '{field}' must be {expected_type.__name__}, got {type(value).__name__}",
                        field=f"{section_path}.{field}",
                        value=value
                    ))
        
        # Check constraints
        if "constraints" in schema:
            for field, constraint in schema["constraints"].items():
                if field in section:
                    value = section[field]
                    
                    if "min" in constraint and value < constraint["min"]:
                        errors.append(ValidationError(
                            f"Field '{field}' must be >= {constraint['min']}, got {value}",
                            field=f"{section_path}.{field}",
                            value=value
                        ))
                    
                    if "max" in constraint and value > constraint["max"]:
                        errors.append(ValidationError(
                            f"Field '{field}' must be <= {constraint['max']}, got {value}",
                            field=f"{section_path}.{field}",
                            value=value
                        ))
                    
                    if "pattern" in constraint:
                        pattern = constraint["pattern"]
                        if not re.match(pattern, str(value)):
                            errors.append(ValidationError(
                                f"Field '{field}' must match pattern {pattern}, got '{value}'",
                                field=f"{section_path}.{field}",
                                value=value
                            ))
        
        # Handle errors
        if errors:
            if collect_all_errors:
                # In a full implementation, we'd collect all errors
                # For now, raise the first one
                raise errors[0]
            else:
                raise errors[0]
    
    @classmethod
    def _validate_references(cls, data: Dict[str, Any]) -> None:
        """Validate cross-references (e.g., use case actor references)."""
        # Build set of actor names if actors section exists
        actor_names = set()
        if "actors" in data and isinstance(data["actors"], list):
            actor_names = {actor["name"] for actor in data["actors"] if "name" in actor}
        
        # Validate use case actor references
        if "use_cases" in data and isinstance(data["use_cases"], list):
            for i, uc in enumerate(data["use_cases"]):
                if "actor" in uc:
                    actor_name = uc["actor"]
                    if actor_names and actor_name not in actor_names:
                        raise ValidationError(
                            f"Use case references unknown actor: '{actor_name}'",
                            field=f"use_cases[{i}].actor",
                            value=actor_name
                        )
    
    @classmethod
    def generate_validation_report(cls, yaml_path: Path) -> Dict[str, Any]:
        """
        Generate a detailed validation report.
        Returns dict with validation results, errors, and warnings.
        """
        report = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "file_path": str(yaml_path),
            "timestamp": None
        }
        
        try:
            data = cls.validate_file(yaml_path)
            report["valid"] = True
            report["data_summary"] = {
                "project": data.get("project", {}).get("name", "Unknown"),
                "domain": data.get("project", {}).get("domain", "Unknown"),
                "actor_count": len(data.get("actors", [])),
                "use_case_count": len(data.get("use_cases", []))
            }
            
            # Generate warnings for common issues
            if "actors" not in data or not data["actors"]:
                report["warnings"].append("No actors defined. System may have no users.")
            
            if "use_cases" not in data or not data["use_cases"]:
                report["warnings"].append("No use cases defined. Project has no functionality.")
            
        except ValidationError as e:
            report["errors"].append({
                "message": str(e),
                "field": e.field,
                "value": str(e.value) if e.value else None
            })
        except Exception as e:
            report["errors"].append({
                "message": f"Unexpected validation error: {e}",
                "field": None,
                "value": None
            })
        
        return report


class CLIArgumentValidator:
    """Validate CLI arguments for UMLAgents commands."""
    
    @staticmethod
    def validate_project_id(project_id: Any) -> int:
        """Validate project ID is a positive integer."""
        try:
            pid = int(project_id)
            if pid <= 0:
                raise ValueError("Project ID must be positive")
            return pid
        except (ValueError, TypeError):
            raise ValidationError(
                f"Project ID must be a positive integer, got '{project_id}'",
                field="project_id",
                value=project_id
            )
    
    @staticmethod
    def validate_yaml_path(yaml_path: str) -> Path:
        """Validate YAML file path exists and has correct extension."""
        path = Path(yaml_path)
        
        if not path.exists():
            raise ValidationError(f"File does not exist: {yaml_path}", field="yaml_file")
        
        if path.suffix.lower() not in ['.yaml', '.yml']:
            raise ValidationError(
                f"File must have .yaml or .yml extension, got {path.suffix}",
                field="yaml_file",
                value=yaml_path
            )
        
        return path
    
    @staticmethod
    def validate_db_path(db_path: str) -> Path:
        """Validate database file path."""
        path = Path(db_path)
        
        # Check if parent directory is writable
        parent = path.parent
        if not parent.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise ValidationError(
                    f"Cannot create database directory: {e}",
                    field="db_path",
                    value=db_path
                )
        
        # Check if directory is writable
        if not os.access(str(parent), os.W_OK):
            raise ValidationError(
                f"Database directory not writable: {parent}",
                field="db_path",
                value=db_path
            )
        
        return path


def format_validation_errors(errors: List[Dict]) -> str:
    """Format validation errors for user-friendly display."""
    if not errors:
        return "No validation errors."
    
    lines = ["Validation errors:"]
    for i, error in enumerate(errors, 1):
        lines.append(f"  {i}. {error['message']}")
        if error.get('field'):
            lines.append(f"     Field: {error['field']}")
        if error.get('value'):
            lines.append(f"     Value: {error['value']}")
    
    return "\n".join(lines)


def format_validation_warnings(warnings: List[str]) -> str:
    """Format validation warnings for user-friendly display."""
    if not warnings:
        return ""
    
    lines = ["Validation warnings:"]
    for i, warning in enumerate(warnings, 1):
        lines.append(f"  {i}. {warning}")
    
    return "\n".join(lines)