
# MSP Autopilot

## Problem Statement

Managed Service Providers manage IT infrastructure for multiple
business customers. Monitoring, investigating and resolving incidents
manually can consume significant engineering time.

MSP Autopilot is an AI-powered IT operations platform that helps
MSPs monitor infrastructure, detect incidents, investigate probable
root causes, recommend remediation actions and verify recovery.

## Main Objectives

1. Monitor customer infrastructure.
2. Detect and organize infrastructure alerts.
3. Classify incidents by severity and priority.
4. Investigate incidents using logs and metrics.
5. Recommend safe remediation actions.
6. Require authorization for sensitive operations.
7. Execute approved actions.
8. Verify whether services have recovered.
9. Maintain an auditable incident history.

## Initial Technology Stack

- Python
- Django REST Framework
- React
- PostgreSQL
- Amazon Bedrock
- Strands Agents
- AWS AgentCore
- Amazon CloudWatch
- Docker

## Core Security Principle

AI agents must not have unrestricted access to customer
infrastructure. All remediation actions must pass through
authorization, policy validation and controlled execution.
