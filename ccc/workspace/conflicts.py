"""Cross-repo inconsistency detection."""
from typing import Dict, List, Set
from dataclasses import dataclass

@dataclass
class Conflict:
    """Represents an inconsistency between services."""
    type: str  # "enum_mismatch", "type_conflict", "api_mismatch"
    symbol: str
    services: List[str]
    details: str

class ConflictDetector:
    """Detect inconsistencies across services."""
    
    def detect_enum_conflicts(self, service_results: Dict) -> List[Conflict]:
        """Find enums defined differently in multiple services."""
        enum_definitions = {}
        
        for service_name, result in service_results.items():
            for enum in result.enums:
                key = enum.name
                if key not in enum_definitions:
                    enum_definitions[key] = []
                enum_definitions[key].append({
                    "service": service_name,
                    "values": enum.values,
                    "file": enum.file,
                })
        
        conflicts = []
        for enum_name, definitions in enum_definitions.items():
            if len(definitions) > 1:
                # Check if values are different
                value_sets = [set(d["values"]) for d in definitions]
                if len(set(frozenset(vs) for vs in value_sets)) > 1:
                    services = [d["service"] for d in definitions]
                    conflicts.append(Conflict(
                        type="enum_mismatch",
                        symbol=enum_name,
                        services=services,
                        details=f"Enum {enum_name} defined differently across services",
                    ))
        
        return conflicts
