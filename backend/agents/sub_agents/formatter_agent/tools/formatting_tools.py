"""
Formatting tools for converting raw data into structured UI-ready formats.
This module centralizes all formatting logic previously scattered across agents.
"""

import json
from typing import Dict, List, Any, Optional, Union


def format_jira_status(issue_key: str) -> Dict[str, str]:
    """
    Format Jira status response for UI consumption.
    
    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123")
        
    Returns:
        Structured JSON for jira_status UI component
    """
    return {"ui": "jira_status", "key": issue_key}


def format_issue_list(title: str, issues: List[Dict[str, Any]], data_source: str = "jira") -> Dict[str, Any]:
    """
    Format issue list response for UI consumption.
    
    Args:
        title: Title for the issue list
        issues: List of issue dictionaries with keys: key, summary, status, priority, url
        data_source: Source of the data (default: "jira")
        
    Returns:
        Structured JSON for issue_list UI component
    """
    formatted_issues = []
    for issue in issues:
        formatted_issue = {
            "key": issue.get("key", ""),
            "summary": issue.get("summary", ""),
            "status": issue.get("status", ""),
            "priority": issue.get("priority", ""),
            "url": issue.get("url", "")
        }
        # Add optional fields if present
        if "assignee" in issue:
            formatted_issue["assignee"] = issue["assignee"]
        if "story_points" in issue:
            formatted_issue["story_points"] = issue["story_points"]
        if "estimated_days" in issue:
            formatted_issue["estimated_days"] = issue["estimated_days"]
            
        formatted_issues.append(formatted_issue)
    
    return {
        "ui": "issue_list",
        "data": {
            "title": title,
            "issues": formatted_issues,
            "source": data_source
        }
    }


def format_user_card(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format user card response for UI consumption.
    
    Args:
        user_data: Dictionary containing user information
        
    Returns:
        Structured JSON for user_card UI component
    """
    return {
        "ui": "user_card",
        "data": {
            "displayName": user_data.get("displayName", ""),
            "emailAddress": user_data.get("emailAddress", ""),
            "avatarUrl": user_data.get("avatarUrl", ""),
            "accountId": user_data.get("accountId", ""),
            "designation": user_data.get("designation", ""),
            "online": user_data.get("online", False)
        }
    }


def format_assignee_response(assignee_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format assignee lookup response for UI consumption.
    
    Args:
        assignee_data: Raw assignee data from tools
        
    Returns:
        Structured JSON for assignee display
    """
    if "ui" in assignee_data and assignee_data["ui"] == "user_card":
        return assignee_data
    
    # Convert raw assignee data to user_card format
    return format_user_card(assignee_data)


def format_eta_response(eta_data: Dict[str, Any], issue_key: str = "") -> Dict[str, Any]:
    """
    Format ETA/timeline response for UI consumption.
    
    Args:
        eta_data: Raw ETA data containing optimistic/pessimistic estimates
        issue_key: Optional issue key for context
        
    Returns:
        Structured JSON for ETA display
    """
    return {
        "ui": "eta_estimate",
        "data": {
            "issue_key": issue_key,
            "optimistic_days": eta_data.get("optimistic_days", 0),
            "pessimistic_days": eta_data.get("pessimistic_days", 0),
            "estimated_completion": eta_data.get("estimated_completion", ""),
            "confidence": eta_data.get("confidence", "medium"),
            "factors": eta_data.get("factors", [])
        }
    }


def format_cpa_summary(cpa_data: Dict[str, Any], project_key: str = "") -> Dict[str, Any]:
    """
    Format Critical Path Analysis summary for UI consumption.
    
    Args:
        cpa_data: Raw CPA analysis data
        project_key: Optional project key for context
        
    Returns:
        Structured JSON for CPA summary display
    """
    return {
        "ui": "cpa_summary",
        "data": {
            "project_key": project_key,
            "critical_path": cpa_data.get("critical_path", []),
            "total_duration": cpa_data.get("total_duration", 0),
            "bottlenecks": cpa_data.get("bottlenecks", []),
            "risk_factors": cpa_data.get("risk_factors", []),
            "recommendations": cpa_data.get("recommendations", [])
        }
    }


def format_sprint_summary(sprint_data: Dict[str, Any], project_key: str = "") -> Dict[str, Any]:
    """
    Format sprint summary for UI consumption.
    
    Args:
        sprint_data: Raw sprint data
        project_key: Optional project key for context
        
    Returns:
        Structured JSON for sprint summary display
    """
    return {
        "ui": "sprint_summary",
        "data": {
            "project_key": project_key,
            "sprint_name": sprint_data.get("sprint_name", ""),
            "start_date": sprint_data.get("start_date", ""),
            "end_date": sprint_data.get("end_date", ""),
            "total_issues": sprint_data.get("total_issues", 0),
            "completed_issues": sprint_data.get("completed_issues", 0),
            "in_progress_issues": sprint_data.get("in_progress_issues", 0),
            "todo_issues": sprint_data.get("todo_issues", 0),
            "story_points": sprint_data.get("story_points", {}),
            "issues": sprint_data.get("issues", [])
        }
    }


def format_issue_details(issue_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format detailed issue information for UI consumption.
    
    Args:
        issue_data: Raw issue data
        
    Returns:
        Structured JSON for issue details display
    """
    return {
        "ui": "issue_details",
        "data": {
            "key": issue_data.get("key", ""),
            "summary": issue_data.get("summary", ""),
            "description": issue_data.get("description", ""),
            "status": issue_data.get("status", ""),
            "priority": issue_data.get("priority", ""),
            "assignee": issue_data.get("assignee", {}),
            "reporter": issue_data.get("reporter", {}),
            "created": issue_data.get("created", ""),
            "updated": issue_data.get("updated", ""),
            "due_date": issue_data.get("due_date", ""),
            "story_points": issue_data.get("story_points", 0),
            "labels": issue_data.get("labels", []),
            "components": issue_data.get("components", []),
            "blockers": issue_data.get("blockers", []),
            "dependencies": issue_data.get("dependencies", []),
            "comments": issue_data.get("comments", [])
        }
    }


def format_dependency_graph(graph_data: Dict[str, Any], issue_key: str = "") -> Dict[str, Any]:
    """
    Format dependency graph for UI consumption.
    
    Args:
        graph_data: Raw dependency graph data
        issue_key: Optional root issue key
        
    Returns:
        Structured JSON for dependency graph display
    """
    return {
        "ui": "dependency_graph",
        "data": {
            "root_issue": issue_key,
            "nodes": graph_data.get("nodes", []),
            "edges": graph_data.get("edges", []),
            "critical_path": graph_data.get("critical_path", []),
            "layout": graph_data.get("layout", "hierarchical")
        }
    }


def format_error_response(error_message: str, error_type: str = "general", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Format error response for UI consumption.
    
    Args:
        error_message: Human-readable error message
        error_type: Type of error (general, validation, api, etc.)
        context: Optional context information
        
    Returns:
        Structured JSON for error display
    """
    return {
        "ui": "error",
        "data": {
            "message": error_message,
            "type": error_type,
            "context": context or {},
            "timestamp": ""  # Could add timestamp if needed
        }
    }


def format_generic_response(data: Any, response_type: str = "data", title: str = "") -> Dict[str, Any]:
    """
    Format generic response for UI consumption when no specific formatter applies.
    
    Args:
        data: Raw data to format
        response_type: Type of response (data, text, json, etc.)
        title: Optional title for the response
        
    Returns:
        Structured JSON for generic display
    """
    return {
        "ui": "generic",
        "data": {
            "type": response_type,
            "title": title,
            "content": data
        }
    }


def format_response_with_context(raw_data: Any, user_input: str, agent_output: str = "") -> Dict[str, Any]:
    """
    Smart formatter that determines the best format based on context.
    
    Args:
        raw_data: Raw data from agent tools
        user_input: Original user input for context
        agent_output: Optional agent output for additional context
        
    Returns:
        Appropriately formatted response
    """
    user_input_lower = user_input.lower()
    
    # Determine format based on user intent and data structure
    if isinstance(raw_data, dict):
        # Check if already formatted
        if "ui" in raw_data:
            return raw_data
            
        # Check for specific patterns in user input
        if "status" in user_input_lower and "issue" in user_input_lower:
            # Extract issue key from user input or data
            issue_key = ""
            if "key" in raw_data:
                issue_key = raw_data["key"]
            else:
                # Try to extract from user input
                words = user_input.split()
                for word in words:
                    if "-" in word and word.replace("-", "").replace("_", "").isalnum():
                        issue_key = word
                        break
            return format_jira_status(issue_key)
            
        elif "assignee" in user_input_lower or "assigned" in user_input_lower:
            return format_assignee_response(raw_data)
            
        elif "eta" in user_input_lower or "when" in user_input_lower or "complete" in user_input_lower:
            return format_eta_response(raw_data)
            
        elif "issues" in raw_data and isinstance(raw_data["issues"], list):
            title = raw_data.get("title", "Issues")
            return format_issue_list(title, raw_data["issues"])
            
        elif "critical_path" in raw_data or "cpa" in user_input_lower:
            return format_cpa_summary(raw_data)
            
        elif "sprint" in user_input_lower:
            return format_sprint_summary(raw_data)
            
        elif "key" in raw_data and "summary" in raw_data:
            return format_issue_details(raw_data)
    
    # Default to generic formatting
    return format_generic_response(raw_data, "json" if isinstance(raw_data, (dict, list)) else "text")
