"""WebSocket connection manager for real-time customer support messaging.

Tracks connected clients (customers, CS agents, RD agents) and routes messages
between them. Handles ticket assignment, escalation, and service lifecycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket

from database import (
    insert_message,
    insert_ticket,
    assign_ticket_cs,
    assign_ticket_rd,
    update_ticket_customer,
    end_ticket_service,
    list_active_tickets_for_agent,
    get_ticket,
)
from models import TicketStatus

logger = logging.getLogger("ws_manager")


class WSClients:
    """In-memory registry of all connected WebSocket clients."""

    def __init__(self):
        self.customers: dict[str, WebSocket] = {}       # customer_id -> ws
        self.cs_agents: dict[str, WebSocket] = {}       # cs_username -> ws
        self.rd_agents: dict[str, WebSocket] = {}       # rd_username -> ws
        self.ticket_map: dict[int, str] = {}            # ticket_id -> customer_id
        self.ticket_cs: dict[int, str] = {}             # ticket_id -> cs_username
        self.ticket_rd: dict[int, str] = {}             # ticket_id -> rd_username

    # --- Registration ---

    DEFAULT_CS = "小陈"

    async def register_customer(self, customer_id: str, ws: WebSocket) -> int:
        """Register a customer connection. Returns a new ticket_id."""
        self.customers[customer_id] = ws
        ticket_id = insert_ticket({
            "title": f"客户 {customer_id} 咨询",
            "description": "",
            "status": TicketStatus.PENDING.value,
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        update_ticket_customer(ticket_id, customer_id)
        self.ticket_map[ticket_id] = customer_id

        # Always assign to default CS
        cs_name = self.DEFAULT_CS
        assign_ticket_cs(ticket_id, cs_name)
        self.ticket_cs[ticket_id] = cs_name
        update_ticket_status_db(ticket_id, TicketStatus.PENDING.value)
        return ticket_id

    async def register_cs(self, username: str, ws: WebSocket):
        self.cs_agents[username] = ws

    async def register_rd(self, username: str, ws: WebSocket):
        self.rd_agents[username] = ws

    # --- Deregistration ---

    async def unregister_customer(self, customer_id: str):
        self.customers.pop(customer_id, None)

    async def unregister_cs(self, username: str):
        self.cs_agents.pop(username, None)

    async def unregister_rd(self, username: str):
        self.rd_agents.pop(username, None)

    # --- Routing ---

    async def send_to_customer(self, ticket_id: int, message: dict):
        customer_id = self.ticket_map.get(ticket_id)
        if customer_id and customer_id in self.customers:
            ws = self.customers[customer_id]
            await ws.send_json(message)

    async def send_to_cs(self, ticket_id: int, message: dict):
        cs_name = self.ticket_cs.get(ticket_id)
        if cs_name and cs_name in self.cs_agents:
            ws = self.cs_agents[cs_name]
            await ws.send_json(message)

    async def send_to_rd(self, ticket_id: int, message: dict):
        rd_name = self.ticket_rd.get(ticket_id)
        if rd_name and rd_name in self.rd_agents:
            ws = self.rd_agents[rd_name]
            await ws.send_json(message)

    async def send_to_all_rd(self, message: dict):
        for ws in self.rd_agents.values():
            await ws.send_json(message)

    async def send_to_all_cs(self, message: dict):
        for ws in self.cs_agents.values():
            await ws.send_json(message)

    # --- Business Logic ---

    async def handle_customer_message(self, ticket_id: int, content: str, customer_id: str):
        """Customer sends a message → persist + forward to assigned CS."""
        insert_message(ticket_id, "customer", customer_id, content)
        ticket = get_ticket(ticket_id)
        cs_name = self.ticket_cs.get(ticket_id)
        if not cs_name and self.cs_agents:
            cs_name = next(iter(self.cs_agents))
            assign_ticket_cs(ticket_id, cs_name)
            self.ticket_cs[ticket_id] = cs_name
            update_ticket_status_db(ticket_id, TicketStatus.PENDING.value)

        msg = {
            "type": "customer_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": content,
                "sender_name": customer_id,
                "ticket_title": ticket.get("title", "") if ticket else "",
            },
        }
        await self.send_to_cs(ticket_id, msg)

    async def handle_agent_message(self, ticket_id: int, content: str, sender_type: str, sender_name: str):
        """CS or RD sends a message → persist + forward to customer."""
        insert_message(ticket_id, sender_type, sender_name, content)
        msg = {
            "type": "agent_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": content,
                "sender_name": sender_name,
                "sender_type": sender_type,
            },
        }
        await self.send_to_customer(ticket_id, msg)

    async def handle_escalate(self, ticket_id: int, reason: str = ""):
        """CS escalates ticket to RD. Notify RD agents, remove CS from ticket."""
        from database import escalate_ticket as db_escalate
        db_escalate(ticket_id, reason or "客服主动升级")
        insert_message(ticket_id, "system", "系统", "正在为您升级工单，工程师即将接入")
        update_ticket_status_db(ticket_id, TicketStatus.ESCALATED.value)

        # Notify customer
        await self.send_to_customer(ticket_id, {
            "type": "system_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": "正在为您升级工单，工程师即将接入",
            },
        })

        # Notify CS to exit
        cs_name = self.ticket_cs.get(ticket_id)
        if cs_name and cs_name in self.cs_agents:
            await self.cs_agents[cs_name].send_json({
                "type": "escalation_transfer",
                "payload": {"ticket_id": ticket_id, "action": "exit"},
            })
        self.ticket_cs.pop(ticket_id, None)

        # Notify all RD agents
        ticket = get_ticket(ticket_id)
        await self.send_to_all_rd({
            "type": "new_escalation",
            "payload": {
                "ticket_id": ticket_id,
                "title": ticket.get("title", "") if ticket else "",
                "reason": reason,
            },
        })

    async def handle_rd_accept(self, ticket_id: int, rd_name: str):
        """RD accepts an escalated ticket. Takes over the conversation."""
        assign_ticket_rd(ticket_id, rd_name)
        self.ticket_rd[ticket_id] = rd_name
        update_ticket_status_db(ticket_id, TicketStatus.AI_PROCESSING.value)
        insert_message(ticket_id, "system", "系统", f"工程师 {rd_name} 为您服务")

        await self.send_to_customer(ticket_id, {
            "type": "system_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": f"工程师 {rd_name} 为您服务",
            },
        })

    async def handle_service_end(self, ticket_id: int):
        """Agent ends service. Notify customer to fill satisfaction survey."""
        end_ticket_service(ticket_id)
        insert_message(ticket_id, "system", "系统", "服务已结束")

        await self.send_to_customer(ticket_id, {
            "type": "service_end",
            "payload": {
                "ticket_id": ticket_id,
                "content": "您的问题是否已解决？",
            },
        })

        # Notify both CS and RD to clean up
        cs_name = self.ticket_cs.pop(ticket_id, None)
        if cs_name and cs_name in self.cs_agents:
            await self.cs_agents[cs_name].send_json({
                "type": "ticket_closed",
                "payload": {"ticket_id": ticket_id},
            })
        rd_name = self.ticket_rd.pop(ticket_id, None)
        if rd_name and rd_name in self.rd_agents:
            await self.rd_agents[rd_name].send_json({
                "type": "ticket_closed",
                "payload": {"ticket_id": ticket_id},
            })

    async def handle_satisfaction(self, ticket_id: int, resolved: str, feedback_text: str = ""):
        """Customer submits satisfaction feedback."""
        from database import insert_satisfaction_feedback
        insert_satisfaction_feedback(ticket_id, resolved, feedback_text)

    def get_available_cs_count(self) -> int:
        return len(self.cs_agents)

    def get_available_rd_count(self) -> int:
        return len(self.rd_agents)


def update_ticket_status_db(ticket_id: int, status: str):
    """Update ticket status in database."""
    from database import update_ticket_status
    update_ticket_status(ticket_id, status)


# Singleton
clients = WSClients()
