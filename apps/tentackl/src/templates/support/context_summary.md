# Support Ticket Context Summary

## Ticket #{{ ticket_id }}

**Subject**: {{ subject }}
**From**: {{ customer_email }}
**Received**: {{ received_at }}
**Source**: {{ source }}

---

## Ticket Analysis

| Analysis | Result |
|----------|--------|
| **Category** | {{ category }} |
| **Severity** | {{ severity }} |
| **Priority** | {{ priority }} |
| **Suggested SLA** | {{ suggested_sla }} |

### Category Reasoning
{{ category_reasoning }}

### Severity Reasoning
{{ severity_reasoning }}

---

## Customer Context

### Account Information

| Field | Value |
|-------|-------|
| **Customer** | {{ customer_name }} |
| **Email** | {{ customer_email }} |
| **Plan Tier** | {{ plan_tier }} |
| **Account Status** | {{ account_status }} |
| **Credits Remaining** | {{ credits_remaining }} |
| **Member Since** | {{ member_since }} |
| **Last Login** | {{ last_login }} |

---

### Recent API Errors (Last 24h)

{{ error_summary }}

{% if recent_errors %}
| Time | Error Type | Message |
|------|------------|---------|
{% for error in recent_errors %}
| {{ error.timestamp }} | {{ error.type }} | {{ error.message }} |
{% endfor %}
{% else %}
*No recent API errors found.*
{% endif %}

---

### Recent Workflows (Last 24h)

{{ workflow_summary }}

{% if recent_workflows %}
| ID | Goal | Status | Created |
|----|------|--------|---------|
{% for workflow in recent_workflows %}
| {{ workflow.id }} | {{ workflow.goal }} | {{ workflow.status }} | {{ workflow.created_at }} |
{% endfor %}
{% else %}
*No recent workflows found.*
{% endif %}

---

## Original Ticket Body

```
{{ ticket_body }}
```

---

## AI Suggested Response

{{ ai_suggested_response }}

---

## Recommended Actions

{% for action in recommended_actions %}
- [ ] {{ action }}
{% endfor %}

---

*Context generated automatically by Support Automation at {{ generated_at }}*
*Task ID: {{ task_id }}*
